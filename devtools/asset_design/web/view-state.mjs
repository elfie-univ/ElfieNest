// One view state is owned by the asset page and applied by its embedded viewer.
export const defaultView = Object.freeze({
  module: 'all', floor: 'all', section: false, glass: true, scale: true,
  furniture: true, dimensions: false, ruler: false, light: 'day', camera: 'fit',
});
const house = value => /^M\d{2}$/.test(value);
const cameras = ['fit', 'front', 'top', 'rear', 'side'];
const switches = ['glass', 'scale', 'furniture', 'dimensions', 'ruler'];

export function deriveCapabilities(records) {
  const modules = {};
  for (const properties of records) {
    const module = properties.module;
    if (module !== 'central' && !house(module)) continue;
    if (properties.reference) continue;
    const floor = Number(properties.floor || 1);
    if (!Number.isInteger(floor) || floor < 1) continue;
    (modules[module] ||= new Set()).add(String(floor));
  }
  return Object.fromEntries(Object.entries(modules).map(([module, floors]) =>
    [module, [...floors].sort((a, b) => Number(a) - Number(b))]));
}

export function objectChoices(capabilities) {
  const modules = Object.keys(capabilities);
  const houses = modules.filter(house).sort();
  const choices = [{value: 'all', label: modules.length > 1 ? '园区整体' : '完整模型'}];
  if (modules.includes('central')) choices.push({value: 'central', label: '主楼'});
  if (houses.length > 1) choices.push({value: 'pods', label: `${houses.length} 间小屋合看`});
  for (const module of houses) choices.push({value: module, label: `小屋 ${module}`});
  return choices;
}

export function floorChoices(capabilities, module) {
  let floors = capabilities[module] || [];
  if (module === 'pods') {
    const groups = Object.entries(capabilities).filter(([name]) => house(name)).map(([, values]) => values);
    floors = groups.length ? groups[0].filter(floor => groups.every(values => values.includes(floor))) : [];
  }
  const names = {'1': '一楼', '2': '二楼', '3': '三楼'};
  return [{value: 'all', label: '全部楼层'}, ...floors.map(floor => ({
    value: floor,
    label: module === 'central' && floor === '4' ? '屋顶'
      : (house(module) || module === 'pods') && floor === '2' ? '二楼露台'
      : names[floor] || `${floor} 楼`,
  }))];
}

export function normalizeView(input, capabilities) {
  const view = {...defaultView, ...input};
  if (!objectChoices(capabilities).some(choice => choice.value === view.module)) view.module = 'all';
  if (!floorChoices(capabilities, view.module).some(choice => choice.value === view.floor)) view.floor = 'all';
  if (!cameras.includes(view.camera)) view.camera = 'fit';
  if (!['day', 'dusk'].includes(view.light)) view.light = 'day';
  for (const key of ['section', ...switches]) view[key] = typeof view[key] === 'boolean' ? view[key] : defaultView[key];
  return view;
}

export function readView(params) {
  const view = {...defaultView, module: params.get('object') || 'all', floor: params.get('floor') || 'all',
    section: params.get('cut') === '1', light: params.get('light') || 'day', camera: params.get('camera') || 'fit'};
  for (const key of switches) if (params.has(key)) view[key] = params.get(key) === '1';
  return view;
}

export function writeView(params, view) {
  params.set('object', view.module); params.set('floor', view.floor);
  params.set('cut', view.section ? '1' : '0'); params.set('light', view.light); params.set('camera', view.camera);
  for (const key of switches) params.set(key, view[key] ? '1' : '0');
  return params;
}

export function previewChoices(asset) {
  const choices = [];
  if (asset.primaryModel) choices.push({value: 'model', label: '完整模型'});
  const names = {bedding_component: '被褥与枕头', bed_with_bedding: '床体与软装',
    bed_component: '床体', desk_component: '桌柜', chair_component: '椅子'};
  for (const file of asset.models) {
    if (file === asset.primaryModel) continue;
    const name = file.split('/').pop();
    choices.push({value: `glb:${file}`, label: `独立部件 · ${names[name.replace(/\.(glb|gltf)$/i, '')] || name}`});
  }
  if (asset.images.length) choices.push({value: 'images', label: '保存效果图'});
  return choices;
}

export function moduleSelected(selected, actual) {
  return selected === 'all' || selected === actual || selected === 'pods' && house(actual);
}

export function frameable(properties, name, capabilities) {
  if (properties.reference || /backdrop|background|presentation/i.test(name)) return false;
  return !Object.keys(capabilities).length || Object.hasOwn(capabilities, properties.module);
}

export function measurementVisible(entry, view, range) {
  if (!moduleSelected(view.module, entry.module)) return false;
  if (view.floor === 'all') return true;
  return !!range && Math.min(entry.a[2],entry.b[2]) >= range[0] - .05
    && Math.max(entry.a[2],entry.b[2]) <= range[1] + .05;
}

export function meshVisible(properties, view) {
  const floorSurface = properties.roof_floor_extension
    || /structural terrace slab|inset terrace walking finish/i.test(properties.source_name || '');
  return moduleSelected(view.module, properties.module)
    && (!view.section || !properties.section_hide || floorSurface)
    && (view.glass || !properties.glass)
    && (view.scale || !properties.reference)
    && (view.furniture || !properties.furniture)
    && (view.floor === 'all' || properties.full_height
      || Number(properties.floor || 1) === Number(view.floor));
}
