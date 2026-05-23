"""Pluggable cleansing proposal generators (extra beyond deterministic + LLM).

The base cleansing pipeline in ``app.cleansing.proposer`` always runs first;
modules here add specialized proposals (e.g. map_to_cdisc) when the column
shape suggests it.
"""
