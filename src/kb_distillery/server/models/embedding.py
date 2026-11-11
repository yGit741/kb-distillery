"""GET /api/embedding — mirrors kb_distillery.services.embedding.build_embedding_report()."""
from kb_distillery.server.models.base import ApiModel


class EmbeddingPage(ApiModel):
    slug: str
    title: str


class EmbeddingPoint(ApiModel):
    slug: str
    title: str
    x: float                      # 0..1, first principal component (= pc[0])
    y: float                      # 0..1, second principal component (= pc[1])
    pc: list[float] = []          # 0..1 along each of the first components, in order
    cluster: int


class EmbeddingCluster(ApiModel):
    id: int                       # 0 = the largest cluster
    size: int
    cohesion: float               # mean cosine of its pages to its centre
    central: list[EmbeddingPage]  # the pages closest to the centre, best first


class EmbeddingComponent(ApiModel):
    index: int                    # 0 = the direction of largest variance
    variance: float               # share of the total variance, 0..1
    cumulative: float             # share explained by this component and the ones before it
    low: list[EmbeddingPage]      # the pages at its low end
    high: list[EmbeddingPage]     # the pages at its high end


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
    spectrum: list[float] = []    # share of variance per principal component, largest first
    effective_dim: float = 0.0    # participation ratio: how many directions the variance is spread over
    mean_cosine: float = 0.0      # mean cosine between two pages; near 1 = all vectors point the same way
    components: list[EmbeddingComponent] = []
