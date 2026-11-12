import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { Vector3, Triangle, Matrix4 } from '../../../../devtools/web/node_modules/three/build/three.module.js';
import { MeshoptSimplifier } from '../../../../devtools/web/node_modules/three/examples/jsm/libs/meshopt_simplifier.module.js';

export { fs, path, assert, Vector3, Triangle, Matrix4, MeshoptSimplifier };
export const root = fileURLToPath(new URL('../../../../', import.meta.url));
const scratch = path.join(root, 'build/godot_assets/nest-authoring');
export const task = fs.realpathSync(process.argv[2]);
assert(task.startsWith(scratch + path.sep), 'Use a new directory beneath the authoring build folder');
export const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const widths = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4 };
const types = { 5121: Uint8Array, 5123: Uint16Array, 5125: Uint32Array, 5126: Float32Array };

export class Model {
  constructor(file) {
    this.file = file;
    this.raw = fs.readFileSync(file);
    const length = this.raw.readUInt32LE(12);
    this.doc = JSON.parse(this.raw.subarray(20, 20 + length));
    this.binary = this.raw.subarray(28 + length);
    assert(!this.doc.animations && !this.doc.skins);
    assert((this.doc.images ?? []).every(image => image.uri));
    this.original = structuredClone(this.doc);
    this.arrays = this.doc.accessors.map((accessor, id) => this.read(id));
  }

  read(id) {
    const accessor = this.doc.accessors[id];
    const view = this.doc.bufferViews[accessor.bufferView];
    assert(!accessor.sparse && !accessor.extensions);
    const ctor = types[accessor.componentType];
    const bytes = widths[accessor.type] * ctor.BYTES_PER_ELEMENT;
    const offset = (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
    const buffer = Buffer.alloc(accessor.count * bytes);
    for (let i = 0; i < accessor.count; i++) {
      this.binary.copy(buffer, i * bytes, offset + i * (view.byteStride ?? bytes), offset + i * (view.byteStride ?? bytes) + bytes);
    }
    return new ctor(buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.length));
  }

  add(array, type, normalized = false, position = false) {
    const componentType = [...Object.entries(types)].find(([, ctor]) => array instanceof ctor)?.[0];
    assert(componentType, array.constructor.name);
    const accessor = { componentType: Number(componentType), type, count: array.length / widths[type] };
    if (normalized) accessor.normalized = true;
    if (position) {
      accessor.min = [Infinity, Infinity, Infinity];
      accessor.max = [-Infinity, -Infinity, -Infinity];
      for (let i = 0; i < array.length; i++) {
        accessor.min[i % 3] = Math.min(accessor.min[i % 3], array[i]);
        accessor.max[i % 3] = Math.max(accessor.max[i % 3], array[i]);
      }
    }
    this.doc.accessors.push(accessor);
    this.arrays.push(array);
    return this.arrays.length - 1;
  }

  primitive(mesh, part = 0) { return this.doc.meshes[mesh].primitives[part]; }
  positions(primitive) { return this.arrays[primitive.attributes.POSITION]; }
  sourceName(mesh) {
    const node = this.doc.nodes.find(node => node.mesh === mesh);
    return node?.extras?.source_name ?? node?.name ?? this.doc.meshes[mesh].name;
  }

  compactPrimitive(primitive, indices) {
    const used = [...new Set(indices)];
    const remap = new Map(used.map((value, index) => [value, index]));
    for (const [semantic, id] of Object.entries(primitive.attributes)) {
      const accessor = this.doc.accessors[id];
      const old = this.arrays[id];
      const width = widths[accessor.type];
      const next = new old.constructor(used.length * width);
      used.forEach((vertex, i) => next.set(old.subarray(vertex * width, (vertex + 1) * width), i * width));
      primitive.attributes[semantic] = this.add(next, accessor.type, !!accessor.normalized, semantic === 'POSITION');
    }
    const ctor = used.length < 255 ? Uint8Array : used.length < 65535 ? Uint16Array : Uint32Array;
    primitive.indices = this.add(ctor.from(indices, value => remap.get(value)), 'SCALAR');
  }

  save(file) {
    const doc = structuredClone(this.doc);
    const used = [...new Set(doc.meshes.flatMap(mesh => mesh.primitives.flatMap(primitive => [primitive.indices, ...Object.values(primitive.attributes)])))];
    const views = [], chunks = [], accessors = [], mapping = new Map(), canonical = new Map();
    let length = 0;
    for (const id of used) {
      const accessor = { ...doc.accessors[id] };
      delete accessor.bufferView; delete accessor.byteOffset;
      const array = this.arrays[id];
      const bytes = Buffer.from(array.buffer, array.byteOffset, array.byteLength);
      const key = JSON.stringify(accessor) + ':' + sha(bytes);
      if (canonical.has(key)) { mapping.set(id, canonical.get(key)); continue; }
      const pad = (-length) & 3;
      chunks.push(Buffer.alloc(pad), bytes);
      length += pad;
      accessor.bufferView = views.length;
      views.push({ buffer: 0, byteOffset: length, byteLength: bytes.length });
      length += bytes.length;
      const next = accessors.length;
      accessors.push(accessor); mapping.set(id, next); canonical.set(key, next);
    }
    for (const mesh of doc.meshes) for (const primitive of mesh.primitives) {
      primitive.indices = mapping.get(primitive.indices);
      for (const semantic of Object.keys(primitive.attributes)) primitive.attributes[semantic] = mapping.get(primitive.attributes[semantic]);
    }
    doc.accessors = accessors; doc.bufferViews = views; doc.buffers = [{ byteLength: length }];
    const encoded = Buffer.from(JSON.stringify(doc));
    const json = Buffer.concat([encoded, Buffer.alloc((-encoded.length) & 3, 32)]);
    const binary = Buffer.concat([...chunks, Buffer.alloc((-length) & 3)]);
    const header = Buffer.alloc(28 + json.length);
    [0x46546c67, 2, header.length + binary.length, json.length, 0x4e4f534a].forEach((v, i) => header.writeUInt32LE(v, i * 4));
    json.copy(header, 20);
    header.writeUInt32LE(binary.length, 20 + json.length);
    header.writeUInt32LE(0x004e4942, 24 + json.length);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, Buffer.concat([header, binary]));
    return { bytes: header.length + binary.length, sha256: sha(fs.readFileSync(file)) };
  }

  metrics() {
    return {
      uniqueTriangles: this.doc.meshes.reduce((sum, mesh) => sum + mesh.primitives.reduce((count, primitive) => count + this.arrays[primitive.indices].length / 3, 0), 0),
      nodes: this.doc.nodes.length,
      meshes: this.doc.meshes.length,
      materials: this.doc.materials.length,
    };
  }
}

export function makeTree(positions, indices) {
  const triangles = [];
  for (let i = 0; i < indices.length; i += 3) {
    const vertices = [0, 1, 2].map(k => Array.from(positions.subarray(indices[i + k] * 3, indices[i + k] * 3 + 3)));
    if (new Set(indices.subarray(i, i + 3)).size !== 3) continue;
    triangles.push({ vertices, face: i / 3 });
  }
  function build(items) {
    const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (const triangle of items) for (const p of triangle.vertices) for (let k = 0; k < 3; k++) {
      min[k] = Math.min(min[k], p[k]); max[k] = Math.max(max[k], p[k]);
    }
    if (items.length <= 8) return { min, max, triangles: items };
    const axis = max.map((v, k) => v - min[k]).reduce((best, value, k, spans) => value > spans[best] ? k : best, 0);
    items.sort((a, b) => a.vertices.reduce((s, p) => s + p[axis], 0) - b.vertices.reduce((s, p) => s + p[axis], 0));
    const half = items.length >> 1;
    return { min, max, left: build(items.slice(0, half)), right: build(items.slice(half)) };
  }
  const tree = build(triangles);
  const triangle = new Triangle(), point = new Vector3(), hit = new Vector3(), bary = new Vector3();
  return function nearest(input) {
    point.fromArray(input);
    let distance2 = Infinity, face = -1, position, weights;
    const bound = node => input.reduce((sum, value, k) => sum + Math.max(0, node.min[k] - value, value - node.max[k]) ** 2, 0);
    function visit(node, lower) {
      if (lower >= distance2) return;
      if (node.triangles) {
        for (const candidate of node.triangles) {
          triangle.a.fromArray(candidate.vertices[0]); triangle.b.fromArray(candidate.vertices[1]); triangle.c.fromArray(candidate.vertices[2]);
          triangle.closestPointToPoint(point, hit);
          const error = point.distanceToSquared(hit);
          if (error < distance2) {
            distance2 = error; face = candidate.face; position = hit.toArray();
            triangle.getBarycoord(hit, bary); weights = bary.toArray();
          }
        }
      } else {
        const left = bound(node.left), right = bound(node.right);
        if (left < right) { visit(node.left, left); visit(node.right, right); }
        else { visit(node.right, right); visit(node.left, left); }
      }
    }
    visit(tree, 0);
    return { distance: Math.sqrt(distance2), face, position, weights };
  };
}

export function surfaceErrors(sourcePositions, sourceIndices, targetPositions, targetIndices, limit = 10000, tolerance = Infinity) {
  const nearest = makeTree(targetPositions, targetIndices);
  const samples = [];
  const failures = new Set();
  const vertexCount = sourcePositions.length / 3;
  const add = (point, vertices) => { const error=nearest(point).distance; samples.push(error); if(error>tolerance)for(const vertex of vertices)failures.add(vertex); };
  const step = Math.max(1, Math.floor(vertexCount / limit));
  for (let i = 0; i < vertexCount; i += step) add(Array.from(sourcePositions.subarray(i * 3, i * 3 + 3)), [i]);
  const faceStep = Math.max(1, Math.floor(sourceIndices.length / 3 / limit));
  for (let i = 0; i < sourceIndices.length; i += 3 * faceStep) {
    add([0, 1, 2].map(k => (sourcePositions[3 * sourceIndices[i] + k] + sourcePositions[3 * sourceIndices[i + 1] + k] + sourcePositions[3 * sourceIndices[i + 2] + k]) / 3), Array.from(sourceIndices.subarray(i,i+3)));
  }
  samples.sort((a, b) => a - b);
  return { samples: samples.length, max: samples.at(-1), p99: samples[Math.floor(samples.length * .99)], failures: [...failures] };
}

export function boundary(positions, indices) {
  const count = positions.length / 3;
  const edges = new Map();
  for (let i = 0; i < indices.length; i += 3) for (let k = 0; k < 3; k++) {
    const a = indices[i + k], b = indices[i + (k + 1) % 3];
    const key = Math.min(a, b) * count + Math.max(a, b);
    edges.set(key, (edges.get(key) ?? 0) + 1);
  }
  return [...edges].filter(([, tally]) => tally === 1).map(([key]) => [Math.floor(key / count), key % count]);
}

export async function simplify(model, mesh, part, report, threshold = .001) {
  const primitive = model.primitive(mesh, part);
  const oldIndices = new Uint32Array(model.arrays[primitive.indices]);
  if (oldIndices.length < 1500 || primitive.targets) return;
  const oldPositions = model.positions(primitive);
  const vertexCount = oldPositions.length / 3;
  const channels = Object.entries(primitive.attributes).filter(([key]) => key !== 'POSITION');
  const stride = channels.reduce((sum, [, id]) => sum + widths[model.doc.accessors[id].type], 0);
  const attributes = new Float32Array(vertexCount * stride), weights = [];
  let offset = 0;
  for (const [semantic, id] of channels) {
    const accessor = model.doc.accessors[id], width = widths[accessor.type], array = model.arrays[id];
    const normalized = accessor.normalized ? (accessor.componentType === 5121 ? 255 : 65535) : 1;
    for (let i = 0; i < vertexCount; i++) for (let k = 0; k < width; k++) attributes[i * stride + offset + k] = array[i * width + k] / normalized;
    const weight = semantic === 'NORMAL' ? .02 : semantic === 'COLOR_0' ? .1 : .05;
    weights.push(...Array(width).fill(weight));
    offset += width;
  }
  const locks = new Uint8Array(vertexCount);
  const edges = boundary(oldPositions, oldIndices);
  for (const [a, b] of edges) { locks[a] = 1; locks[b] = 1; }
  // Keep original extrema and all primitive boundaries exactly.
  for (let k = 0; k < 3; k++) {
    let min = 0, max = 0;
    for (let i = 1; i < vertexCount; i++) {
      if (oldPositions[i * 3 + k] < oldPositions[min * 3 + k]) min = i;
      if (oldPositions[i * 3 + k] > oldPositions[max * 3 + k]) max = i;
    }
    locks[min] = 1; locks[max] = 1;
  }
  await MeshoptSimplifier.ready;
  const geometricEdges = edges => {
    const tally = new Map();
    const vertex = id => Array.from(oldPositions.subarray(id*3,id*3+3), value=>value===0?0:value).join(',');
    for(const [a,b] of edges) {
      const va=vertex(a),vb=vertex(b);
      if(va===vb)continue;
      const key=va<vb?va+'|'+vb:vb+'|'+va;
      tally.set(key,(tally.get(key)??0)+1);
    }
    return [...tally].filter(([,count])=>count%2!==0).map(([key])=>key).sort();
  };
  const beforeEdges=JSON.stringify(geometricEdges(edges));
  const row = { mesh, part, name: model.sourceName(mesh), before: oldIndices.length / 3, boundaryEdges: edges.length, accepted: false, attempts: [] };
  report.push(row);
  for(let pass=0;pass<15;pass++) {
    const [indices, error] = MeshoptSimplifier.simplifyWithAttributes(oldIndices, oldPositions, 3, attributes, stride, weights, locks, Math.floor(oldIndices.length * .15 / 3) * 3, threshold * .2, ['LockBorder', 'ErrorAbsolute']);
    row.candidate=indices.length/3;
    row.meshoptError=error;
    if (indices.length > oldIndices.length * .96) { row.reason = 'small reduction'; return; }
    const newEdges=boundary(oldPositions, indices);
    row.geometricBoundaryExact=JSON.stringify(geometricEdges(newEdges))===beforeEdges;
    if(!row.geometricBoundaryExact) {
      const extra=new Set(newEdges.flat());
      for(const vertex of extra)locks[vertex]=1;
      row.attempts.push({candidate:indices.length/3,reason:'pin additional boundary vertices'});
      continue;
    }
    const forward=surfaceErrors(oldPositions, oldIndices, oldPositions, indices,10000,threshold);
    const reverse=surfaceErrors(oldPositions, indices, oldPositions, oldIndices,10000,threshold);
    const failures=new Set([...forward.failures,...reverse.failures]);
    delete forward.failures;delete reverse.failures;
    row.forward=forward;row.reverse=reverse;
    row.attempts.push({candidate:indices.length/3,maxDistance:Math.max(forward.max,reverse.max),pinnedFailures:failures.size});
    if(failures.size===0) {
      model.compactPrimitive(primitive,indices);
      row.accepted=true;delete row.reason;return;
    }
    // Preserve the one-ring neighborhood around any measured local defect.
    const adjacent=new Set(failures);
    for(let i=0;i<oldIndices.length;i+=3) {
      if(failures.has(oldIndices[i])||failures.has(oldIndices[i+1])||failures.has(oldIndices[i+2]))
        for(let k=0;k<3;k++)adjacent.add(oldIndices[i+k]);
    }
    for(const vertex of adjacent)locks[vertex]=1;
    row.reason='surface-distance limit';
  }
}
