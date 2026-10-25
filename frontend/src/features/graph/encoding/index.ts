/**
 * The shared graph encoding: how a page looks as a node on every surface (Full Graph, Home, page mini graph,
 * citation view, explorer chips). Other surfaces import from here only, never from the Full Graph's features.
 */
export * from "./spec";
export * from "./canvas";
export * from "./theme";
export * from "./label";
export { NodeMarkSvg, ShapeIcon, SourceIcon, GLYPH_SVG } from "./NodeMarkSvg";
