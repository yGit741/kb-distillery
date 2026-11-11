"""GET /api/embedding — mirrors kb_distillery.services.embedding.build_embedding_report()."""
from kb_distillery.server.models.base import ApiModel


class EmbeddingPage(ApiModel):
    slug: str
    title: str


class EmbeddingPoint(ApiModel):
    slug: str
    title: str
    x: float                      # 0..1, first principal direction
    y: float                      # 0..1, second principal direction
    cluster: int


class EmbeddingCluster(ApiModel):
    id: int                       # 0 = the largest cluster
    size: int
    cohesion: float               # mean cosine of its pages to its centre
    central: list[EmbeddingPage]  # the pages closest to the centre, best first


class EmbeddingDuplicate(ApiModel):
    a: EmbeddingPage
    b: EmbeddingPage
    cosine: float


class EmbeddingReport(ApiModel):
    built: bool                   # False: no vector store yet
    ok: bool                      # the store exists and matches the cards
    line: str                     # the one-line status `vectors status` prints
    model: str | None = None
    dim: int
    cards: int
    vectors: int
    missing: list[EmbeddingPage]  # cards without a vector
    changed: list[EmbeddingPage]  # cards edited since their vector was made
    removed: list[EmbeddingPage]  # vectors whose card is gone
    duplicate_cosine: float       # the threshold `duplicates` uses
    duplicates: list[EmbeddingDuplicate]
    k: int
    silhouette: float
    clusters: list[EmbeddingCluster]
    points: list[EmbeddingPoint]
