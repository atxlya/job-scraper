// Company logos: web/src/logos/<slug>.svg or .png, bundled at build time.
// Nothing is fetched from other sites; a company without a file gets colored initials.
const files = import.meta.glob<string>("./logos/*.{svg,png}", { eager: true, query: "?url", import: "default" });

const bySlug = new Map(
  Object.entries(files).map(([path, url]) => [path.replace(/^.*\/|\.(svg|png)$/g, ""), url]),
);

export function logoFor(slug: string): string | null {
  return bySlug.get(slug) ?? null;
}
