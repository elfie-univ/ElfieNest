// Shared view filtering used by every model in the approved workbench.
export function meshVisible(properties, view) {
  return (view.module === 'all' || properties.module === view.module)
    && (!view.section || !properties.section_hide)
    && (view.glass || !properties.glass)
    && (view.scale || !properties.reference)
    && (view.furniture || !properties.furniture)
    && (view.floor === 'all' || properties.full_height
      || Number(properties.floor || 1) === Number(view.floor));
}
