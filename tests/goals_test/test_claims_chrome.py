"""Run 13 item 12: Wikipedia nav/infobox chrome must not become claims. The strings
below are the exact chrome-carrying sentences behind Run 12's entities."""
from goals.handlers.research_claims import _extract_claims, _strip_chrome
from goals.model import Goal


def test_nav_chrome_is_cut_to_the_sentence_after_it():
    s = ("biology portal Category v t e Evolutionary biology is a subfield of biology "
         "that analyzes the four mechanisms of evolution.")
    assert _strip_chrome(s).startswith("Evolutionary biology is a subfield")
    assert _strip_chrome("H65 2016 Preceded by Ego is the Enemy Website dailystoic.") == ""


def test_extracted_entities_carry_no_chrome():
    g = Goal(id="g", title="Understand history more deeply", kind="research",
             spec={"question": "What about history do I still not understand?"})
    txt = ("Modern Future History portal Category v t e History is the systematic study "
           "of the past. H65 2016 Preceded by Ego is the Enemy Website history.")
    c = _extract_claims(g, [("https://en.wikipedia.org/wiki/History", txt)])
    assert c["relations"] and c["relations"][0]["subject"] == "History"
    assert not any(k in e for e in c["entities"] for k in ("v t e", "Category", "portal", "Website"))
