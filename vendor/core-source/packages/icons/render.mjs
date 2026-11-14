/** Original Core UI icon rendering. No catalog or glyphs are imported here. */
const escape = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
/** @param {import('./types.d.mts').IconDefinition} icon @param {import('./types.d.mts').IconOptions} [options] */
export function renderIcon(
  icon,
  { size = 24, title, decorative = title === undefined, className } = {},
) {
  if (!icon || icon.viewBox !== "0 0 24 24" || typeof icon.body !== "string")
    throw new TypeError("Expected a Core icon definition");
  if (!Number.isFinite(size) || size < 1 || size > 1024)
    throw new RangeError("Icon size must be between 1 and 1024");
  if (!decorative && (typeof title !== "string" || !title.trim()))
    throw new TypeError("An informative icon needs a nonempty title");
  const accessible = decorative
    ? ' aria-hidden="true"'
    : ` role="img" aria-label="${escape(title)}"`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" focusable="false"${accessible}${className ? ` class="${escape(className)}"` : ""}>${decorative ? "" : `<title>${escape(title)}</title>`}${icon.body}</svg>`;
}
