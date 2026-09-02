import pytest

from src.knowledge.base import KnowledgeBaseStore


@pytest.mark.asyncio
async def test_knowledge_search_is_relevant_and_campaign_scoped(tmp_path):
    store = KnowledgeBaseStore(db_path=str(tmp_path / "knowledge.db"))
    await store.add_document(
        "campaign-a",
        name="pricing.md",
        content="The Growth plan costs 500 dollars per month and includes priority support.",
        content_type="text/markdown",
    )
    await store.add_document(
        "campaign-b",
        name="private.txt",
        content="The secret enterprise discount is 90 percent.",
    )

    matches = await store.search("campaign-a", "What does the Growth plan cost?")

    assert matches
    assert matches[0]["document_name"] == "pricing.md"
    assert "500 dollars" in matches[0]["content"]
    assert all("secret enterprise" not in item["content"] for item in matches)


@pytest.mark.asyncio
async def test_duplicate_document_content_is_idempotent_per_campaign(tmp_path):
    store = KnowledgeBaseStore(db_path=str(tmp_path / "knowledge.db"))
    first = await store.add_document("campaign-a", name="one.txt", content="Same facts")
    second = await store.add_document("campaign-a", name="two.txt", content="Same facts")

    assert second["id"] == first["id"]
    assert len(await store.list_documents("campaign-a")) == 1
