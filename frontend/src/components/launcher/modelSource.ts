/**
 * Finds out whether a CAD launcher model exists, without a config flag.
 *
 * A missing file cannot be detected from the status code alone: the Vite dev
 * server answers unknown paths with index.html and a 200. So the bytes are
 * checked for a glTF signature, and the same bytes are handed to the loader -
 * the model is downloaded once.
 */

import { useEffect, useState } from "react";
import type { Group } from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

export type ModelSource =
  | { kind: "loading" }
  | { kind: "placeholder"; reason: string }
  | { kind: "cad"; scene: Group };

/** "glTF", little-endian - the first four bytes of every .glb. */
const GLB_MAGIC = 0x46546c67;

export function looksLikeGltf(buffer: ArrayBuffer): boolean {
  if (
    buffer.byteLength >= 4 &&
    new DataView(buffer).getUint32(0, true) === GLB_MAGIC
  ) {
    return true;
  }
  // A .gltf is JSON. An HTML fallback page starts with "<".
  const head = String.fromCharCode(...new Uint8Array(buffer.slice(0, 64)));
  return head.trimStart().startsWith("{");
}

type Fetcher = (url: string) => Promise<Pick<Response, "ok" | "arrayBuffer">>;
type Parser = (buffer: ArrayBuffer, basePath: string) => Promise<{ scene: Group }>;

const parseGltf: Parser = (buffer, basePath) =>
  new GLTFLoader().parseAsync(buffer, basePath);

export async function loadModelSource(
  url: string,
  fetcher: Fetcher = (u) => fetch(u),
  parse: Parser = parseGltf,
): Promise<ModelSource> {
  const absent: ModelSource = {
    kind: "placeholder",
    reason: `No CAD model at ${url}`,
  };
  let buffer: ArrayBuffer;
  try {
    const response = await fetcher(url);
    if (!response.ok) return absent;
    buffer = await response.arrayBuffer();
  } catch {
    return absent;
  }
  if (!looksLikeGltf(buffer)) return absent;

  try {
    const gltf = await parse(buffer, url.slice(0, url.lastIndexOf("/") + 1));
    return { kind: "cad", scene: gltf.scene };
  } catch (error) {
    console.warn(`Launcher model at ${url} failed to load`, error);
    return { kind: "placeholder", reason: `CAD model at ${url} failed to load` };
  }
}

// One download per URL for the life of the page, however often the view mounts.
const cache = new Map<string, Promise<ModelSource>>();

export function useLauncherModelSource(url: string): ModelSource {
  const [source, setSource] = useState<ModelSource>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    if (!cache.has(url)) cache.set(url, loadModelSource(url));
    void cache.get(url)!.then((result) => {
      if (!cancelled) setSource(result);
    });
    return () => {
      cancelled = true;
    };
  }, [url]);
  return source;
}
