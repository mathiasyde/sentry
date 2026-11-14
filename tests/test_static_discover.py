"""core/static linking: exposed methods, inheritance, the pre-API-17 rule and class resolution."""

from __future__ import annotations

import sys
import unittest

from tests.helpers import SENTRY_DIR

sys.path.insert(0, str(SENTRY_DIR))

from core.static.dataflow import ADD, REMOVE, TOP, CallSiteFact  # noqa: E402
from core.static.discover import Site, link  # noqa: E402
from tests.static_asm import ADD_IDX, FakeIndex, decl  # noqa: E402

BASE, SUB, PLAIN, OTHER = "Lcom/x/Base;", "Lcom/x/Sub;", "Lcom/x/Plain;", "Lcom/x/Other;"
INDEX = FakeIndex(
    {
        BASE: ("Ljava/lang/Object;", [decl("getToken"), decl("showData"), decl("hidden", public=False)]),
        SUB: (BASE, [decl("showData", annotated=False), decl("extra", params=("Ljava/lang/String;",))]),
        PLAIN: ("Ljava/lang/Object;", [decl("publicThing", annotated=False)]),
        OTHER: ("Ljava/lang/Object;", [decl("ping")]),
    }
)


def site(names, objects, kind=ADD, offset=0) -> Site:
    fact = CallSiteFact(offset, kind, ADD_IDX, frozenset(names), frozenset(objects))
    call_site = {"class": "com.x.Main", "method": "init", "signature": "init()", "dex": "classes.dex", "offset": offset}
    return Site(fact, call_site, "verified")


def names_of(methods) -> list[str]:
    return [m["name"] for m in methods]


class Linking(unittest.TestCase):
    def test_inheritance_and_override_hiding(self) -> None:
        result = link([site({("str", "A", None)}, {("new", SUB)})], INDEX, 33)
        (reg,) = result["registrations"]
        self.assertEqual((reg["name"], reg["class_name"], reg["class_resolution"]), ("A", "com.x.Sub", "exact"))
        self.assertEqual(names_of(reg["methods"]), ["extra", "getToken"])  # showData hidden by the override
        token = next(m for m in reg["methods"] if m["name"] == "getToken")
        self.assertEqual((token["declared_in"], token["sensitive"], token["exposure"]), ("com.x.Base", True, "annotation"))
        self.assertEqual(reg["methods"][0]["params"], ["java.lang.String"])

    def test_private_annotated_method_is_not_exposed(self) -> None:
        result = link([], INDEX, 33)
        base = next(c for c in result["bridge_classes"] if c["class_name"] == "com.x.Base")
        self.assertEqual(names_of(base["methods"]), ["getToken", "showData"])
        self.assertFalse(base["methods"][1]["sensitive"])

    def test_pre_17_exposes_all_public_methods(self) -> None:
        (reg,) = link([site({("str", "A", None)}, {("new", PLAIN)})], INDEX, 16)["registrations"]
        self.assertEqual([(m["name"], m["exposure"]) for m in reg["methods"]], [("publicThing", "public-pre-17")])
        (reg,) = link([site({("str", "A", None)}, {("new", PLAIN)})], INDEX, None)["registrations"]
        self.assertEqual(reg["methods"], [])

    def test_unregistered_classes_are_listed(self) -> None:
        result = link([site({("str", "A", None)}, {("new", OTHER)})], INDEX, 33)
        registered = {c["class_name"]: c["registered"] for c in result["bridge_classes"]}
        self.assertEqual(registered, {"com.x.Base": False, "com.x.Other": True, "com.x.Sub": False})
        self.assertEqual([c["class_name"] for c in result["bridge_classes"]], sorted(registered))

    def test_declared_type_and_ambiguity(self) -> None:
        (reg,) = link([site({("str", "A", None)}, {("param", 0, OTHER)})], INDEX, 33)["registrations"]
        self.assertEqual((reg["class_name"], reg["class_resolution"]), ("com.x.Other", "declared-type"))
        (reg,) = link([site({("str", "A", None)}, {("param", 1, "Ljava/lang/Object;")})], INDEX, 33)["registrations"]
        self.assertEqual((reg["class_name"], reg["class_resolution"]), (None, "ambiguous"))
        self.assertEqual(reg["candidate_classes"], ["com.x.Base", "com.x.Other", "com.x.Sub"])
        self.assertEqual(reg["methods"], [])

    def test_unresolved_name_and_sorting(self) -> None:
        sites = [
            site({("result", "com.x.Cfg.bridgeName()", "Ljava/lang/String;")}, {("new", OTHER)}, offset=9),
            site({("str", "B", None), ("str", "A", "com.x.Cfg.NAME")}, {("new", OTHER)}, offset=3),
        ]
        regs = link(sites, INDEX, 33)["registrations"]
        self.assertEqual([r["name"] for r in regs], [None, "A", "B"])
        self.assertEqual(regs[0]["name_status"], "unresolved")
        self.assertEqual(regs[0]["name_source"], {"kind": "method-result", "ref": "com.x.Cfg.bridgeName()"})
        self.assertEqual(regs[1]["name_source"], {"kind": "static-field", "ref": "com.x.Cfg.NAME"})
        self.assertEqual(regs[2]["name_source"], {"kind": "const-string", "ref": None})

    def test_unknown_object_and_removals(self) -> None:
        result = link([site({TOP}, {TOP}), site({("str", "A", None)}, set(), kind=REMOVE)], INDEX, 33)
        (reg,) = result["registrations"]
        self.assertEqual(reg["name_source"], {"kind": "unknown", "ref": None})
        self.assertEqual(reg["class_resolution"], "ambiguous")  # an unknown object may be any bridge class
        (removal,) = result["removals"]
        self.assertEqual((removal["name"], removal["name_status"]), ("A", "resolved"))


if __name__ == "__main__":
    unittest.main()
