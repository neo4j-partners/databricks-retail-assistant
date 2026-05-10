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
    "macbook-coding-mouse": {
        "answer": (
            "The best match is the Logitech MX Master 3S for Mac. It fits a "
            "MacBook coding workflow with quiet clicks, high-resolution "
            "scrolling, USB-C charging, and strong app-specific shortcuts."
        ),
        "summary": "Ranked mouse recommendations for MacBook coding work.",
        "products": [
            ProductCard(
                id="sample-mx-master-3s-mac",
                name="Logitech MX Master 3S for Mac",
                brand="Logitech",
                category="Mouse",
                price=99.99,
                in_stock=True,
                score=0.94,
                rationale="Best ergonomic fit for long coding sessions on macOS.",
                signals=["macOS gestures", "quiet clicks", "USB-C", "ergonomic"],
            ),
            ProductCard(
                id="sample-magic-mouse",
                name="Apple Magic Mouse",
                brand="Apple",
                category="Mouse",
                price=79.0,
                in_stock=True,
                score=0.81,
                rationale="Native Apple gesture support with a compact profile.",
                signals=["native macOS", "multi-touch", "portable"],
            ),
        ],
    },
    "frequent-traveler-headphones": {
        "answer": (
            "For frequent travel, pick the Bose QuietComfort Ultra Headphones. "
            "They prioritize noise cancellation, comfort, and simple multipoint "
            "Bluetooth behavior for airport and hotel workflows."
        ),
        "summary": "Ranked headphones for frequent travelers.",
        "products": [
            ProductCard(
                id="sample-bose-qc-ultra",
                name="Bose QuietComfort Ultra Headphones",
                brand="Bose",
                category="Headphones",
                price=429.0,
                in_stock=True,
                score=0.93,
                rationale="Strong travel comfort and top-tier noise cancellation.",
                signals=["ANC", "multipoint", "folding case", "long-haul comfort"],
            ),
            ProductCard(
                id="sample-sony-xm5",
                name="Sony WH-1000XM5",
                brand="Sony",
                category="Headphones",
                price=399.99,
                in_stock=True,
                score=0.89,
                rationale="Excellent battery life and adaptive noise control.",
                signals=["ANC", "30-hour battery", "lightweight"],
            ),
        ],
    },
}


DIAGNOSIS_PRESETS = {
    "headphones-disconnect-calls": {
        "answer": (
            "The disconnects are most likely caused by multipoint Bluetooth "
            "handoff during call start. Disable multipoint temporarily, forget "
            "and re-pair the headset, then update firmware before the next call."
        ),
        "summary": "Bluetooth call disconnects point to multipoint handoff.",
        "symptom": "Headphones disconnect when calls begin.",
        "solution": "Reset Bluetooth pairing, disable multipoint, and update firmware.",
    },
    "printer-offline": {
        "answer": (
            "The printer is likely marked offline because the network address "
            "changed or the print queue cached a stale connection. Rejoin Wi-Fi, "
            "restart the spooler, and re-add the printer if it still shows offline."
        ),
        "summary": "Offline printer state likely comes from stale network routing.",
        "symptom": "Printer appears offline even while powered on.",
        "solution": "Reconnect Wi-Fi, restart the print queue, and re-add the device.",
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
