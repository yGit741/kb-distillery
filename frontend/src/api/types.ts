/**
 * Response and request types. Generated: `pixi run api-schema` rewrites schema.d.ts from the FastAPI
 * routers; this file only gives its schemas short names. Do not hand-write a response shape.
 */
import type { components } from "./schema";

type S = components["schemas"];

// lifecycle + share
export type LifecycleSnapshot = S["LifecycleSnapshot"];
export type TimelineRow = S["TimelineRow"];
export type SnapshotTag = S["SnapshotTag"];
export type InfraBranch = S["InfraBranch"];
export type StaleWorktree = S["StaleWorktree"];
export type WorkingState = S["WorkingState"];
export type NightlyState = S["NightlyState"];
export type ShareStatus = S["ShareStatus"];
export type ShareChip = S["ShareChip"];
export type CommitKind = TimelineRow["kind"];

// graph, pages, search, path
export type GraphSnapshot = S["GraphSnapshot"];
export type GraphNode = S["GraphNode"];
export type GraphLink = S["GraphLink"];
export type PageIndex = S["PageIndex"];
export type PageCard = S["PageCard"];
export type PageDetail = S["PageDetail"];
export type SearchResult = S["SearchResult"];
export type SearchHit = S["SearchHit"];
export type PathResult = S["PathResult"];

// corpus, raw, citations, pipeline, health, ops
export type CorpusTable = S["CorpusTable"];
export type CorpusRow = S["CorpusRow"];
export type RawPreview = S["RawPreview"];
export type RawCard = S["RawCard"];
export type DigestResult = S["DigestResult"];
export type CitationGraph = S["CitationGraph"];
export type PipelineSnapshot = S["PipelineSnapshot"];
export type HealthSnapshot = S["HealthSnapshot"];
export type OpsSnapshot = S["OpsSnapshot"];

// scopes
export type ScopeList = S["ScopeList"];
export type ScopeDetail = S["ScopeDetail"];
export type ScopeResolved = S["ScopeResolved"];
export type ScopeRow = ScopeDetail["rows"][number];
export type ScopeSummary = ScopeList["scopes"][number];
export type ScopeStep = S["ScopeStep"];
export type ScopeSaveRequest = S["ScopeSaveRequest"];
export type ScopeResolveRequest = S["ScopeResolveRequest"];
export type ScopeDuplicateRequest = S["ScopeDuplicateRequest"];

// chat
export type ChatRequest = S["ChatRequest"];
export type ChatStatus = S["ChatStatus"];
export type ChatSettings = S["ChatSettings"];
export type ChatSettingsUpdate = S["ChatSettingsUpdate"];
export type KeyList = S["KeyList"];
export type KeyAdd = S["KeyAdd"];
export type PromptsResponse = S["PromptsResponse"];
export type SavedChat = S["SavedChat"];
export type SavedChatResult = S["SavedChatResult"];
