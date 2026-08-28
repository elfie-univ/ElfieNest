export const labKinds = {
  elfie: "elfie",
  nest: "nest",
  unified: "unified",
} as const;

export type LabKind = (typeof labKinds)[keyof typeof labKinds];

declare global {
  interface Window {
    __ELFIENEST_LAB__?: string;
    elfieLabEnqueue?: (payload: string) => void;
  }
}

export function currentLabKind(): LabKind {
  switch (window.__ELFIENEST_LAB__) {
    case labKinds.elfie:
      return labKinds.elfie;
    case labKinds.nest:
      return labKinds.nest;
    case labKinds.unified:
      return labKinds.unified;
    default:
      throw new Error("未识别的 Developer Tool 页面入口");
  }
}
