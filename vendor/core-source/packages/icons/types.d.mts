/** Each module contains only its own static geometry; importing a glyph never loads the catalog. */
export interface IconDefinition {
  readonly id: string;
  readonly title: string;
  readonly category: string;
  readonly tags: readonly string[];
  readonly viewBox: "0 0 24 24";
  readonly body: string;
}
export interface IconOptions {
  /** 1–1024 CSS pixels; default 24. */
  size?: number;
  /** Required when decorative=false; supplying a title makes an icon informative by default. */
  title?: string;
  decorative?: boolean;
  className?: string;
}
