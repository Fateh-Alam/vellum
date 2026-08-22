from dataclasses import replace
import unittest

from vellum.core.config import TopicParsingConfig
from vellum.topics.ids import tag_signature
from vellum.topics.parser import TopicParser


class TopicParserTests(unittest.TestCase):
    def test_anking_root_priority_beats_deeper_secondary_path(self) -> None:
        parser = TopicParser()
        result = parser.parse(
            [
                "#AK_Step1_v12::#Pathoma::Renal::Very_Deep::Secondary::Path",
                "#AK_Step1_v12::#FirstAid::10_Renal::04_Pathology::ADTKD",
            ]
        )
        self.assertTrue(result.found)
        self.assertEqual(result.source_root, "#FirstAid")
        self.assertEqual(result.path, ("Renal", "Pathology", "ADTKD"))
        self.assertEqual(result.source_badges, ("First Aid", "Pathoma"))

    def test_generic_fallback_keeps_unconfigured_root(self) -> None:
        result = TopicParser().parse(
            ["Medicine::Renal::Tubulointerstitial::ADTKD"]
        )
        self.assertIsNone(result.source_root)
        self.assertEqual(
            result.path, ("Medicine", "Renal", "Tubulointerstitial", "ADTKD")
        )
        self.assertEqual(
            result.raw_prefixes,
            (
                "Medicine",
                "Medicine::Renal",
                "Medicine::Renal::Tubulointerstitial",
                "Medicine::Renal::Tubulointerstitial::ADTKD",
            ),
        )

    def test_anking_utility_hierarchies_are_not_topics(self) -> None:
        parser = TopicParser(
            replace(TopicParsingConfig(), generic_fallback=False)
        )
        result = parser.parse(
            ["#AK_Step1_v13::$AnKingUpdates::2026-08-20::Changed"]
        )
        self.assertFalse(result.found)

    def test_version_tolerant_source_aliases(self) -> None:
        parser = TopicParser()
        bnb = parser.parse(["#AK_Step1_v42::#BnB::Cardiology::Arrhythmias"])
        sketchy = parser.parse(
            ["#AK_Step1_v42::#SketchyMicro::01_Bacteria::01_Gram_Positive"]
        )
        self.assertEqual(bnb.source_root, "#B&B")
        self.assertEqual(bnb.source_badges, ("Boards & Beyond",))
        self.assertEqual(sketchy.source_root, "#Sketchy")
        self.assertEqual(sketchy.path, ("Bacteria", "Gram Positive"))

    def test_ignored_renamed_and_depth_rules_apply(self) -> None:
        config = replace(
            TopicParsingConfig(),
            ignored_segments=("Pathology",),
            renamed_segments={"Tubulointerstitial_Disorders": "TIN disorders"},
            maximum_depth=2,
        )
        result = TopicParser(config).parse(
            [
                "#AK_Step1_v12::#FirstAid::Renal::Pathology::"
                "Tubulointerstitial_Disorders::ADTKD"
            ]
        )
        self.assertEqual(result.path, ("Renal", "TIN disorders"))
        self.assertEqual(result.canonical_path, ("renal", "tubulointerstitial disorders"))
        self.assertEqual(
            result.raw_prefixes,
            (
                "#AK_Step1_v12::#FirstAid::Renal",
                "#AK_Step1_v12::#FirstAid::Renal::Pathology::Tubulointerstitial_Disorders",
            ),
        )

    def test_display_rename_does_not_change_topic_id(self) -> None:
        tags = ["Medicine::Renal::ADTKD"]
        plain = TopicParser().parse(tags)
        renamed = TopicParser(
            replace(TopicParsingConfig(), renamed_segments={"ADTKD": "MUC1 disease"})
        ).parse(tags)
        self.assertEqual(plain.topic_id, renamed.topic_id)
        self.assertNotEqual(plain.path, renamed.path)

    def test_ancestor_ids_are_ordered_from_broad_to_parent(self) -> None:
        result = TopicParser().parse(["Medicine::Renal::Pathology::ADTKD"])
        self.assertEqual(len(result.ancestor_topic_ids), 3)
        self.assertNotIn(result.topic_id, result.ancestor_topic_ids)

    def test_preview_and_empty_state(self) -> None:
        parser = TopicParser()
        self.assertEqual(parser.preview(["Medicine::Renal"]), "Medicine → Renal")
        self.assertEqual(parser.preview(["flat-tag"]), "No topic context found")

    def test_tag_signature_is_order_independent(self) -> None:
        self.assertEqual(tag_signature(["B::C", "A::B"]), tag_signature(["A::B", "B::C"]))


if __name__ == "__main__":
    unittest.main()
