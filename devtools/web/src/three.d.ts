declare module "three" {
  type ThreeObjectParent = {
    position: { x: number; y: number; z: number };
    parent: ThreeObjectParent | null;
  };

  export class Vector3 {
    constructor(x?: number, y?: number, z?: number);
    clone(): Vector3;
    sub(vector: Vector3): this;
    add(vector: Vector3): this;
    copy(vector: Vector3): this;
    length(): number;
    normalize(): this;
    multiplyScalar(value: number): this;
  }

  export class ConeGeometry {
    constructor(radius: number, height: number, radialSegments: number);
    translate(x: number, y: number, z: number): this;
    rotateX(radians: number): this;
  }

  export class CylinderGeometry {
    constructor(radiusTop: number, radiusBottom: number, height: number, radialSegments: number, heightSegments?: number, openEnded?: boolean);
    translate(x: number, y: number, z: number): this;
    rotateX(radians: number): this;
  }

  export class MeshLambertMaterial {
    constructor(parameters?: { color?: string; transparent?: boolean; opacity?: number; depthWrite?: boolean });
    color: { set(value: string): void };
    opacity: number;
    dispose(): void;
  }

  export class Mesh {
    constructor(geometry?: ConeGeometry | CylinderGeometry, material?: MeshLambertMaterial);
    geometry: ConeGeometry | CylinderGeometry;
    material: MeshLambertMaterial;
    renderOrder: number;
    position: { copy(vector: Vector3): void };
    scale: { set(x: number, y: number, z: number): void };
    lookAt(target: Vector3): void;
    visible: boolean;
  }

  export class Group {
    children: unknown[];
    renderOrder: number;
    parent: ThreeObjectParent | null;
    visible: boolean;
    position: { copy(vector: Vector3): void };
    add(object: unknown): void;
    lookAt(target: Vector3): void;
  }

  export class CanvasTexture {
    constructor(image: HTMLCanvasElement);
    dispose(): void;
  }

  export class SpriteMaterial {
    constructor(parameters?: {
      map?: CanvasTexture;
      transparent?: boolean;
      depthWrite?: boolean;
      depthTest?: boolean;
      opacity?: number;
    });
    map?: CanvasTexture;
    dispose(): void;
  }

  export class Sprite {
    constructor(material?: SpriteMaterial);
    material: SpriteMaterial;
    parent: ThreeObjectParent | null;
    onBeforeRender: (renderer: unknown, scene: unknown, camera: { position: { x: number; y: number; z: number } }) => void;
    renderOrder: number;
    visible: boolean;
    position: { x: number; y: number; z: number; set(x: number, y: number, z: number): void };
    scale: { set(x: number, y: number, z: number): void };
  }
}
