"""Medical coding subsystem.

Public API (lazy — import via submodules):

    from app.coding import dictionary
    dictionary.lookup(system, term, top_k=5)
    dictionary.get_code_info(system, code)
    dictionary.list_systems()

The bundled dictionaries cover CC0-licensed cores: ICD-10, ATC, LOINC.
Commercial dictionaries (MedDRA, WHODrug, SNOMED-CT) require a user-configured
local path (``coding.<system>_path`` in ``settings.yaml``) and are **never**
packaged in the repository.
"""
