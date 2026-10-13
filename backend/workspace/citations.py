"""Validate model output strictly against the evidence supplied this turn."""
import json
import re


def interpret_answer(raw,evidence):
    raw=raw[:100_000]
    try:
        payload=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '',raw.strip()))
        answer=payload['answer']
        if not isinstance(answer,str) or not answer.strip():
            raise ValueError()
        if payload.get('insufficient_evidence') is True:
            return answer,[],'evidence_insufficient'
        by_id={source['chunk_id']:source for source in evidence}
        verified=[]
        entries=payload.get('citations',[])
        if not isinstance(entries,list) or not entries or len(entries)>20:
            return answer,[],'unverified'
        for cite in entries:
            source=by_id.get(cite.get('id'))
            quote=cite.get('quote')
            if source is None or not isinstance(quote,str) or not quote.strip() or quote not in source['text']:
                return answer,[],'unverified'
            verified.append({**source,'quote':quote})
        return answer,verified,'citations_verified'
    except (ValueError,KeyError,TypeError,AttributeError):
        return raw,[],'unverified'
