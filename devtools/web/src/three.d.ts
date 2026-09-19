declare module "three" {
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
    visible: boolean;
    position: { set(x: number, y: number, z: number): void };
    scale: { set(x: number, y: number, z: number): void };
  }
}
