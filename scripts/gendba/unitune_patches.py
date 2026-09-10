#!/usr/bin/env python3
"""
unitune_patches.py -- make UniTune importable and runnable for the arms we want.

We harvest UniTune for its META-DECISION: TopAdvisor picks which arm (knob / index /
query / view) gets the next trial, using Thompson sampling over per-arm Beta
posteriors. That decision type exists nowhere else in our corpus. We only need the
`knob` and `index` arms; the other two drag in dependencies this machine does not have.

Applied at runtime so the submodule checkout stays clean, same as udo_patches.py.
"""
from __future__ import annotations

import sys
import types


def stub_jpype():
    """
    MultiTune/advisor/alternative_adviser.py imports .learnedrewrite at module level,
    and learnedrewrite imports jpype -- a Java bridge for the query-rewrite arm. There
    is no JVM on this node, and jpype is only referenced INSIDE functions there, so a
    stub module lets TopAdvisor import while any actual use of the `query` arm fails
    loudly rather than silently doing nothing.
    """
    if "jpype" in sys.modules:
        return
    m = types.ModuleType("jpype")

    def _unavailable(*a, **k):
        raise RuntimeError(
            "jpype is stubbed: the UniTune 'query' (learnedrewrite) arm needs a JVM, "
            "which this node does not have. Harvest the knob and index arms only.")

    for name in ("startJVM", "shutdownJVM", "JClass", "JPackage", "JString",
                 "isJVMStarted", "getDefaultJVMPath", "attachThreadToJVM"):
        setattr(m, name, _unavailable)
    # learnedrewrite does `from jpype.types import *`, so jpype must look like a
    # PACKAGE with submodules, not a bare module.
    m.__path__ = []                       # marks it as a package
    for sub in ("imports", "types", "beans"):
        sm = types.ModuleType(f"jpype.{sub}")
        if sub == "types":
            # names learnedrewrite pulls in via the star-import
            for t in ("JString", "JArray", "JClass", "JObject", "JInt", "JLong",
                      "JDouble", "JBoolean", "JByte", "JChar", "JFloat", "JShort"):
                setattr(sm, t, _unavailable)
        setattr(m, sub, sm)
        sys.modules[f"jpype.{sub}"] = sm
    sys.modules["jpype"] = m


def stub_java_arms():
    """
    alternative_adviser imports all four arms at module level. Two of them are Java:

        learnedrewrite -> jpype
        rl_estimator   -> query_rewrite.rewriter, which at IMPORT TIME shells out to
                          `mvn dependency:build-classpath`, starts a JVM, and does
                          `from javax.sql import DataSource`

    Neither Maven nor a JVM exists on this node, and we only want the knob and index
    arms (dbabandit and ottertune need nothing but openbox). Stubbing the two Java
    modules is one level of faking; stubbing their dependency chain would be four.

    Any attempt to actually USE those arms raises, rather than silently no-opping.
    """
    def _make(name, attrs):
        m = types.ModuleType(name)

        class _Unavailable:
            def __init__(self, *a, **k):
                raise RuntimeError(
                    f"{name} is stubbed: the UniTune query/view arms need a JVM and "
                    "Maven, which this node does not have. Harvest arms=knob,index.")

        for a in attrs:
            setattr(m, a, _Unavailable)
        return m

    for mod, attrs in (("MultiTune.advisor.learnedrewrite", ["LearnedRewrite"]),
                       ("MultiTune.advisor.autoview", ["AutoView"]),
                       ("MultiTune.advisor.rl_estimator", ["RLEstimator"])):
        sys.modules.setdefault(mod, _make(mod, attrs))


def apply():
    stub_jpype()
    stub_java_arms()


if __name__ == "__main__":
    apply()
    sys.path.insert(0, "/proj/pmoss-PG0/protox/unitune/UniTune")
    from MultiTune.advisor.alternative_adviser import TopAdvisor
    import inspect
    src = inspect.getsource(TopAdvisor)
    print("TopAdvisor imports OK")
    print("  arms referenced:", [a for a in ("knob", "index", "query", "view")
                                 if f"'{a}'" in src])
    print("  NOTE: query/view arms are stubbed (no JVM/Maven); use arms=knob,index")
    print("  arm-selection policies:",
          [m for m in ("optimize_ts", "optimize_alter", "optimize_acq", "optimize_rb")
           if hasattr(TopAdvisor, m)])
