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
export type TextSearch = S["TextSearch"];
export type TextHit = S["TextHit"];
export type SimilarResult = S["SimilarResult"];
export type SimilarHit = S["SimilarHit"];
export type PathResult = S["PathResult"];
export type GraphRelation = S["GraphRelation"];
export type NamedQuery = S["NamedQuery"];
export type QueryTable = S["QueryTable"];
export type ShapeResult = S["ShapeResponse"];
export type LayersResult = S["LayersResponse"];
export type StyleSpec = S["StyleSpec"];
export type StyleTarget = S["Target"];
export type RelationProposals = S["RelationProposals"];
export type RelationProposal = S["RelationProposal"];

// corpus, raw, citations, pipeline, health, ops
export type CorpusTable = S["CorpusTable"];
export type CorpusRow = S["CorpusRow"];
export type RawPreview = S["RawPreview"];
export type RawCard = S["RawCard"];
export type DigestResult = S["DigestResult"];
export type CitationGraph = S["CitationGraph"];
export type PipelineSnapshot = S["PipelineSnapshot"];
export type HealthSnapshot = S["HealthSnapshot"];

// the knowledge base behind this app, and the ones the explorer can load
export type KbInfo = S["KbInfo"];
export type KbList = S["KbList"];
export type KbRow = S["KbRow"];
export type KbType = S["KbType"];
export type KbImportPreview = S["KbImportPreview"];
export type KbImportResult = S["KbImportResult"];
export type KbInbox = S["KbInbox"];
export type KbInboxItem = S["KbInboxItem"];
export type KbInboxPull = S["KbInboxPull"];
export type InboxAddResult = S["InboxAddResult"];
export type InboxFileResult = S["InboxFileResult"];
export type LinkFolderResult = S["LinkFolderResult"];
/** The body of the import routes (local app only): a zipped bundle, or a git URL; `id` and `kit` are optional. */
export type KbImportRequest = ({ file: File } | { gitUrl: string }) & { id?: string; kit?: string };
export type ViewList = S["ViewList"];
export type PinnedView = S["View"];
export type ReadyView = S["ReadyView"];
export type ReadyViewList = S["ReadyViewList"];
export type RecentList = S["RecentList"];
export type RecentStep = S["RecentStep"];
export type VideoBundle = S["VideoBundle"];
export type VideoAnchor = S["VideoAnchor"];
export type VideoSection = S["VideoSection"];
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
export type ChatAnswer = S["ChatAnswer"];
export type ChatAnswerResult = S["ChatAnswerResult"];
export type ChatMessageIn = S["ChatMessageIn"];
export type ChatMessageResult = S["ChatMessageResult"];
export type ChatStatus = S["ChatStatus"];
export type ChatSettings = S["ChatSettings"];
export type ChatSettingsUpdate = S["ChatSettingsUpdate"];
export type KeyList = S["KeyList"];
export type KeyAdd = S["KeyAdd"];
export type PromptsResponse = S["PromptsResponse"];
export type SavedChat = S["SavedChat"];
export type SavedChatResult = S["SavedChatResult"];

// chat sessions (kept on this machine under <kb>/.local/sessions)
export type SessionList = S["SessionList"];
export type SessionSummary = S["SessionSummary"];
export type SessionDoc = S["SessionDoc"];
export type SessionPutRequest = S["SessionPutRequest"];
export type SessionDeleted = S["SessionDeleted"];

// chat skills (the kb's whitelist, switched per session)
export type ChatSkillList = S["ChatSkillList"];
export type ChatSkill = S["ChatSkill"];
export type ChatSkillsPut = S["ChatSkillsPut"];

// backlog
export type BacklogList = S["BacklogList"];
export type BacklogItem = S["BacklogItem"];

// think
export type ThinkList = S["ThinkList"];
export type ThinkNote = S["ThinkNote"];
export type ThinkNoteMeta = S["ThinkNoteMeta"];
export type ThinkWriteResult = S["ThinkWriteResult"];
export type ThinkSaveRequest = S["ThinkSaveRequest"];
