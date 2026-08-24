"""Синтаксические экстракторы (по дереву зависимостей Natasha)."""
from __future__ import annotations

from aved.core.models import Evidence, Feature, FeatureValue
from aved.features.extractors.base import (
    ExtractorContext,
    absent,
    rate_per_1000,
    register,
)

_SUBORD_RELS = {"advcl", "acl", "acl:relcl", "ccomp", "xcomp", "csubj"}


def _clause_stats(ctx: ExtractorContext) -> dict[str, int]:
    def compute() -> dict[str, int]:
        sub = coord = asyn = simple = rel_clause = adv_clause = 0
        for sent in ctx.doc.sentences:
            rels = {t.rel for t in sent.tokens}
            pos = {t.pos for t in sent.tokens}
            fin = sum(
                1 for t in sent.tokens
                if t.feats.get("VerbForm") == "Fin"
                or (t.pos == "VERB" and "VerbForm" not in t.feats)
            )
            has_sub = bool(_SUBORD_RELS & rels) or "SCONJ" in pos
            has_cc = "CCONJ" in pos and "conj" in rels
            if "acl:relcl" in rels or "acl" in rels:
                rel_clause += 1
            if "advcl" in rels:
                adv_clause += 1
            if has_sub:
                sub += 1
            elif fin >= 2 and has_cc:
                coord += 1
            elif fin >= 2:
                asyn += 1
            else:
                simple += 1
        return {
            "sub": sub, "coord": coord, "asyn": asyn, "simple": simple,
            "rel_clause": rel_clause, "adv_clause": adv_clause,
            "total": len(ctx.doc.sentences) or 1,
        }

    return ctx.cached("clause_stats", compute)  # type: ignore[return-value]


@register("clause_types")
def clause_types(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    s = _clause_stats(ctx)
    total = s["total"]
    fid = feature.id
    if fid.endswith("subordinate_dominant"):
        present = s["sub"] >= max(s["coord"], s["asyn"], s["simple"]) and s["sub"] > 0
        val, note = s["sub"] / total, f"СПП: {s['sub']}/{total}"
    elif fid.endswith("coordinate"):
        present, val, note = s["coord"] > 0, s["coord"] / total, f"ССП: {s['coord']}"
    elif fid.endswith("asyndetic"):
        present, val, note = s["asyn"] > 0, s["asyn"] / total, f"бессоюзных: {s['asyn']}"
    elif fid.endswith("attributive_clauses"):
        present, val, note = s["rel_clause"] > 0, s["rel_clause"], f"определит.: {s['rel_clause']}"
    elif fid.endswith("adverbial_clauses"):
        present, val, note = s["adv_clause"] > 0, s["adv_clause"], f"обстоят.: {s['adv_clause']}"
    else:
        return absent(feature, note="clause_types: неизвестный признак")
    return FeatureValue(feature_id=fid, present=present, value=round(val, 3),
                        source_kind="auto", note=note)


@register("conjunctions")
def conjunctions(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    sconj = [t for t in ctx.doc.tokens if t.pos == "SCONJ"]
    cconj = [t for t in ctx.doc.tokens if t.pos == "CCONJ"]
    fid = feature.id
    if fid.endswith("subordinating_conj"):
        toks = sconj
    elif fid.endswith("coordinating_conj"):
        toks = cconj
    else:  # союзы/союзные слова как средство связи (nsv.text.conjunction_links)
        toks = sconj + cconj
    ev = [Evidence(t.text, t.start, t.stop) for t in toks[:6]]
    return FeatureValue(
        feature_id=fid, present=len(toks) > 0,
        value=rate_per_1000(len(toks), ctx.doc.word_count()),
        evidence=ev, source_kind="auto", note=f"союзов: {len(toks)}",
    )


@register("passive")
def passive(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    toks = [
        t for t in ctx.doc.tokens
        if t.feats.get("Voice") == "Pass" or "pass" in t.rel
    ]
    ev = [Evidence(t.text, t.start, t.stop) for t in toks[:6]]
    return FeatureValue(feature_id=feature.id, present=len(toks) > 0,
                        value=rate_per_1000(len(toks), ctx.doc.word_count()),
                        evidence=ev, source_kind="auto", note=f"пассивных форм: {len(toks)}")


@register("participial")
def participial(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    toks = [t for t in ctx.doc.words if t.feats.get("VerbForm") in ("Part", "Conv")]
    ev = [Evidence(t.text, t.start, t.stop) for t in toks[:6]]
    return FeatureValue(feature_id=feature.id, present=len(toks) > 0,
                        value=rate_per_1000(len(toks), ctx.doc.word_count()),
                        evidence=ev, source_kind="auto",
                        note=f"причастий/деепричастий: {len(toks)}")


_AGREEMENT_RELS = {"amod", "det", "nummod"}
_GOVERNMENT_RELS = {"obj", "iobj", "obl", "nmod"}
_ADJUNCTION_RELS = {"advmod", "xcomp"}


def _phrase_stats(ctx: ExtractorContext) -> dict[str, int]:
    def compute() -> dict[str, int]:
        verbal = nominal = adverbial = complex_heads = 0
        agree = govern = adjoin = nmod_prepless = 0
        for sent in ctx.doc.sentences:
            dep_count: dict[int, int] = {}
            # карта «вершина -> отношения её детей» для проверки наличия предлога
            children: dict[int, list[str]] = {}
            for i, t in enumerate(sent.tokens):
                if t.head < 0:
                    continue
                dep_count[t.head] = dep_count.get(t.head, 0) + 1
                children.setdefault(t.head, []).append(t.rel)
            for i, t in enumerate(sent.tokens):
                if t.head < 0:
                    continue
                head = sent.tokens[t.head]
                if head.pos == "VERB":
                    verbal += 1
                elif head.pos in ("NOUN", "PROPN", "ADJ", "PRON", "NUM"):
                    nominal += 1
                elif head.pos == "ADV":
                    adverbial += 1
                if t.rel in _AGREEMENT_RELS:
                    agree += 1
                elif t.rel in _GOVERNMENT_RELS:
                    govern += 1
                elif t.rel in _ADJUNCTION_RELS:
                    adjoin += 1
                if t.rel == "nmod" and "case" not in children.get(i, ()):
                    nmod_prepless += 1
            complex_heads += sum(1 for n in dep_count.values() if n >= 2)
        return {
            "verbal": verbal, "nominal": nominal, "adverbial": adverbial,
            "complex": complex_heads, "agree": agree, "govern": govern,
            "adjoin": adjoin, "nmod_prepless": nmod_prepless,
        }

    return ctx.cached("phrase_stats", compute)  # type: ignore[return-value]


@register("phrase_types")
def phrase_types(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    s = _phrase_stats(ctx)
    total = (s["verbal"] + s["nominal"] + s["adverbial"]) or 1
    fid = feature.id
    if fid.endswith("verbal_dominant"):
        present, val = s["verbal"] >= max(s["nominal"], s["adverbial"]) and s["verbal"] > 0, s["verbal"] / total
    elif fid.endswith("nominal"):
        present, val = s["nominal"] > 0, s["nominal"] / total
    elif fid.endswith("adverbial"):
        present, val = s["adverbial"] > 0, s["adverbial"] / total
    elif fid.endswith("complex"):
        present, val = s["complex"] > 0, s["complex"]
    else:
        return absent(feature, note="phrase_types: неизвестный признак")
    return FeatureValue(feature_id=fid, present=present, value=round(val, 3),
                        source_kind="auto")


@register("phrase_relations")
def phrase_relations(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    s = _phrase_stats(ctx)
    total = (s["agree"] + s["govern"] + s["adjoin"]) or 1
    fid = feature.id
    if fid.endswith("adjunction"):
        present, val = s["adjoin"] >= max(s["agree"], s["govern"]) and s["adjoin"] > 0, s["adjoin"] / total
    elif fid.endswith("agreement"):
        present, val = s["agree"] > 0, s["agree"] / total
    elif fid.endswith("government"):
        present, val = s["govern"] >= max(s["agree"], s["adjoin"]) and s["govern"] > 0, s["govern"] / total
    elif "prepositionless" in fid:
        present, val = s["nmod_prepless"] > 0, s["nmod_prepless"]
    else:
        return absent(feature, note="phrase_relations: неизвестный признак")
    return FeatureValue(feature_id=fid, present=present, value=round(val, 3),
                        source_kind="auto")


@register("inversion")
def inversion(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    inv = 0
    evidence: list[Evidence] = []
    for sent in ctx.doc.sentences:
        for t in sent.tokens:
            if t.head < 0:
                continue
            head = sent.tokens[t.head]
            postposed = t.start > head.start
            if (t.rel == "amod" and postposed) or (t.rel == "advmod" and t.pos == "ADV" and postposed):
                inv += 1
                if len(evidence) < 6:
                    evidence.append(Evidence(f"{head.text} {t.text}", head.start, t.stop))
    if feature.id.endswith("direct_order"):
        return FeatureValue(feature_id=feature.id, present=inv == 0, value=inv,
                            source_kind="auto", note=f"инверсий: {inv}")
    return FeatureValue(feature_id=feature.id, present=inv > 0, value=inv,
                        evidence=evidence, source_kind="auto", note=f"инверсий: {inv}")


@register("sentence_extension")
def sentence_extension(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    sents = ctx.doc.sentences
    avg = round(ctx.doc.word_count() / len(sents), 2) if sents else 0.0
    fid = feature.id
    if fid.endswith("brief_unextended"):
        present = 0 < avg < 10
    elif fid.endswith("developed_extension"):
        present = avg >= 18
    else:  # extension_degree — информативный показатель
        present = avg > 0
    return FeatureValue(feature_id=fid, present=present, value=avg,
                        source_kind="auto", note=f"средняя длина предложения: {avg} слов")


@register("homogeneous_members")
def homogeneous_members(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    toks = [t for t in ctx.doc.tokens if t.rel == "conj"]
    ev = [Evidence(t.text, t.start, t.stop) for t in toks[:6]]
    return FeatureValue(feature_id=feature.id, present=len(toks) > 0, value=len(toks),
                        evidence=ev, source_kind="auto", note=f"однородных рядов: {len(toks)}")


def _children_map(sent) -> dict[int, list[int]]:
    ch: dict[int, list[int]] = {}
    for i, t in enumerate(sent.tokens):
        if t.head >= 0:
            ch.setdefault(t.head, []).append(i)
    return ch


def _count_value(feature: Feature, ctx: ExtractorContext, hits: int,
                 evidence: list[Evidence], label: str) -> FeatureValue:
    return FeatureValue(feature_id=feature.id, present=hits > 0,
                        value=rate_per_1000(hits, ctx.doc.word_count()),
                        evidence=evidence[:6], source_kind="auto", note=f"{label}: {hits}")


@register("modality")
def modality(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    from aved.features.extractors.lexicon import _load_lexicon, count_matches
    alpha, phrases = _load_lexicon(str(ctx.data_dir / "lexicons/synt/modality_subjective.txt"))
    hits, ev = count_matches(ctx, alpha, phrases)
    return _count_value(feature, ctx, hits, ev, "средств модальности")


@register("u_genitive")
def u_genitive(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    hits, ev = 0, []
    for sent in ctx.doc.sentences:
        for t in sent.tokens:
            if t.text.lower() == "у" and t.pos == "ADP" and t.head >= 0:
                head = sent.tokens[t.head]
                if head.feats.get("Case") == "Gen":
                    hits += 1
                    ev.append(Evidence(f"у {head.text}", t.start, head.stop))
    return _count_value(feature, ctx, hits, ev, "конструкций «у+род.»")


@register("compound_predicate")
def compound_predicate(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    modals = {"надо", "нужно", "нельзя", "можно", "необходимо", "должен",
              "обязан", "мочь", "хотеть", "следует"}
    hits, ev = 0, []
    for sent in ctx.doc.sentences:
        ch = _children_map(sent)
        for i, t in enumerate(sent.tokens):
            if t.lemma in modals and any(
                sent.tokens[c].feats.get("VerbForm") == "Inf" for c in ch.get(i, [])
            ):
                hits += 1
                ev.append(Evidence(t.text, t.start, t.stop))
    return _count_value(feature, ctx, hits, ev, "модальных сказуемых")


@register("genitive_chains")
def genitive_chains(feature: Feature, ctx: ExtractorContext) -> FeatureValue:
    hits, ev = 0, []
    for sent in ctx.doc.sentences:
        ch = _children_map(sent)
        for i, t in enumerate(sent.tokens):
            if t.pos == "NOUN" and t.feats.get("Case") == "Gen":
                for c in ch.get(i, []):
                    d = sent.tokens[c]
                    if d.rel == "nmod" and d.feats.get("Case") == "Gen":
                        hits += 1
                        ev.append(Evidence(f"{t.text} {d.text}", t.start, d.stop))
    return _count_value(feature, ctx, hits, ev, "цепочек род. падежа")
