from __future__ import annotations

from .models import (
    AgenticSearchOut,
    CitedSource,
    DemoWarning,
    DiagnosisPathStep,
    GraphHop,
    IssueDiagnosisOut,
    KnowledgeChunk,
    MemoryWrite,
    ProductCard,
    ProfileChip,
    RecommendedAction,
    SourceType,
    TimingMetadata,
    ToolTimelineItem,
)


SEARCH_PRESETS = {
    "trail-running-shoes": {
        "answer": (
            "For waterproof trail running under $150, start with the Brooks "
            "Cascadia 17 GTX. It balances wet-weather protection, trail grip, "
            "and enough cushioning for rocky weekend runs."
        ),
        "summary": "Ranked waterproof trail running shoes under $150.",
        "products": [
            ProductCard(
                id="sample-brooks-cascadia-17-gtx",
                name="Cascadia 17 GTX",
                brand="Brooks",
                category="Trail running shoes",
                price=149.0,
                in_stock=True,
                score=0.94,
                rationale="Best balance of waterproofing, grip, and under-$150 pricing.",
                signals=["waterproof", "trail grip", "under $150", "stable"],
            ),
            ProductCard(
                id="sample-pegasus-trail-4",
                name="Pegasus Trail 4 GTX",
                brand="Nike",
                category="Trail running shoes",
                price=140.0,
                in_stock=True,
                score=0.88,
                rationale="Lighter road-to-trail option with weather protection.",
                signals=["waterproof", "road-to-trail", "lightweight"],
            ),
        ],
    },
    "rain-hiking-jacket": {
        "answer": (
            "For a light hiking shell that can handle rain, pick the Stormline "
            "Stretch Rain Shell. It packs small, breathes well, and keeps a "
            "clean feature set for day hikes."
        ),
        "summary": "Ranked lightweight rain shells for day hikes.",
        "products": [
            ProductCard(
                id="sample-stormline-shell",
                name="Stormline Stretch Rain Shell",
                brand="Black Diamond",
                category="Rain jacket",
                price=169.0,
                in_stock=True,
                score=0.91,
                rationale="Strong packability and stretch without overbuilding.",
                signals=["waterproof", "packable", "stretch", "day hike"],
            ),
            ProductCard(
                id="sample-patagonia-torrentshell",
                name="Torrentshell 3L",
                brand="Patagonia",
                category="Rain jacket",
                price=179.0,
                in_stock=True,
                score=0.87,
                rationale="More durable three-layer shell for wetter hikes.",
                signals=["waterproof", "durable", "3-layer"],
            ),
        ],
    },
}


DIAGNOSIS_PRESETS = {
    "running-shoes-feel-flat": {
        "answer": (
            "Running shoes that feel flat after about 300 miles usually have "
            "compressed midsole foam. Rotate in a fresh pair, check outsole "
            "wear, and reserve the old pair for short easy runs if traction is safe."
        ),
        "summary": "Flat ride points to midsole compression after high mileage.",
        "symptom": "Running shoes feel flat and unresponsive after 300 miles.",
        "solution": "Replace or rotate the shoes and inspect outsole traction.",
    },
    "outsole-peeling": {
        "answer": (
            "Outsole peeling after a few months is usually an adhesion or flex "
            "stress issue. Clean and dry the shoe, stop using heat to dry it, "
            "and contact support if the separation is wider than a few millimeters."
        ),
        "summary": "Peeling outsole suggests adhesion failure or high-flex wear.",
        "symptom": "Continental outsole is peeling after three months.",
        "solution": "Avoid heat drying, inspect separation, and start a warranty claim if needed.",
    },
}


def search_sample(
    *,
    preset_id: str | None,
    prompt: str,
    request_id: str,
    session_id: str,
    source_type: SourceType = "sample",
    warning: str | None = None,
) -> AgenticSearchOut:
    preset = SEARCH_PRESETS.get(preset_id or "", _default_search(prompt))
    products = list(preset["products"])
    warnings = _sample_warnings(warning)
    return AgenticSearchOut(
        answer=str(preset["answer"]),
        source_type=source_type,
        trace_source="sample",
        request_id=request_id,
        session_id=session_id,
        warnings=warnings,
        timing=TimingMetadata(total_ms=0),
        summary=str(preset["summary"]),
        product_picks=products,
        related_products=products[1:],
        profile_chips=[
            ProfileChip(label="Intent", value="comparison", kind="session"),
            ProfileChip(label="Channel", value="demo", kind="session"),
        ],
        memory_writes=[
            MemoryWrite(
                label="interest",
                value=products[0].category or "product",
                kind="preference",
                stored=True,
            )
        ],
        tool_timeline=[
            ToolTimelineItem(tool_name="get_user_profile", summary="Loaded demo profile"),
            ToolTimelineItem(tool_name="search_products", summary="Ranked product matches"),
            ToolTimelineItem(tool_name="get_related_products", summary="Found alternatives"),
        ],
        graph_hops=[
            GraphHop(
                source=products[0].name,
                relationship="SIMILAR_TO",
                target=products[-1].name,
                score=0.82,
            )
        ],
        knowledge_chunks=[
            KnowledgeChunk(
                id="sample-search-context",
                text="Demo context combines product attributes, preference signals, and graph relationships.",
                source_type="sample",
                score=0.9,
                features=products[0].signals,
                related_products=[product.name for product in products],
            )
        ],
    )


def diagnosis_sample(
    *,
    preset_id: str | None,
    prompt: str,
    request_id: str,
    session_id: str,
    source_type: SourceType = "sample",
    warning: str | None = None,
) -> IssueDiagnosisOut:
    preset = DIAGNOSIS_PRESETS.get(preset_id or "", _default_diagnosis(prompt))
    symptom = str(preset["symptom"])
    solution = str(preset["solution"])
    warnings = _sample_warnings(warning)
    chunk = KnowledgeChunk(
        id="sample-diagnosis-context",
        text=f"{symptom} Recommended resolution: {solution}",
        source_type="sample",
        score=0.91,
        symptoms=[symptom],
        solutions=[solution],
    )
    return IssueDiagnosisOut(
        answer=str(preset["answer"]),
        source_type=source_type,
        trace_source="sample",
        request_id=request_id,
        session_id=session_id,
        warnings=warnings,
        timing=TimingMetadata(total_ms=0),
        summary=str(preset["summary"]),
        confidence=0.86,
        path=[
            DiagnosisPathStep(label="Symptom", detail=symptom),
            DiagnosisPathStep(label="Likely cause", detail=str(preset["summary"])),
            DiagnosisPathStep(label="Solution", detail=solution),
        ],
        recommended_actions=[
            RecommendedAction(label=solution, priority="high"),
            RecommendedAction(label="Escalate if the issue repeats", priority="medium"),
        ],
        compatible_alternatives=[],
        cited_sources=[
            CitedSource(
                id=chunk.id,
                title="Curated demo support context",
                source_type="sample",
                snippet=chunk.text,
                score=chunk.score,
            )
        ],
        tool_timeline=[
            ToolTimelineItem(tool_name="hybrid_knowledge_search", summary="Matched symptom context"),
            ToolTimelineItem(tool_name="diagnose_product_issue", summary="Mapped symptom to solution"),
        ],
        knowledge_chunks=[chunk],
    )


def _sample_warnings(message: str | None) -> list[DemoWarning]:
    if not message:
        message = "Sample demo data was used."
    return [DemoWarning(code="sample_data_used", message=message)]


def _default_search(prompt: str) -> dict:
    return {
        "answer": f"Sample search response for: {prompt}",
        "summary": "Sample product ranking.",
        "products": [
            ProductCard(
                id="sample-product",
                name="Curated Demo Product",
                brand="Demo",
                category="Retail",
                price=129.0,
                in_stock=True,
                score=0.8,
                rationale="Generic sample product for local development.",
                signals=["sample", "fallback"],
            )
        ],
    }


def _default_diagnosis(prompt: str) -> dict:
    return {
        "answer": f"Sample diagnosis response for: {prompt}",
        "summary": "Sample issue diagnosis.",
        "symptom": prompt,
        "solution": "Run the recommended reset steps and retry.",
    }
