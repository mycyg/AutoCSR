"""Tiny helper used at packaging time to build the bundled CSVs.

Run once with ``python -m app.coding.data._build_csvs`` to regenerate the
three CC0 dictionary files in-place. The output CSVs are committed; this
script exists so the data is reproducible / inspectable.

Keep the lists below conservative — only CC0 public-domain codes.
"""
from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- ICD-10 core
# Public WHO ICD-10 codes (Chapters I..XXI). Codes + preferred terms only.
# Hierarchy uses Chapter|Block titles for grouping.

ICD10: list[tuple[str, str, str]] = []


def _icd_block(chapter: str, block: str, rows: list[tuple[str, str]]) -> None:
    for code, term in rows:
        ICD10.append((code, term, f"{chapter}|{block}"))


# Chapter I — Certain infectious and parasitic diseases (A00–B99)
_icd_block("I Infectious", "Intestinal infections", [
    ("A00", "Cholera"), ("A01", "Typhoid and paratyphoid fevers"),
    ("A02", "Other salmonella infections"), ("A03", "Shigellosis"),
    ("A04", "Other bacterial intestinal infections"),
    ("A05", "Other bacterial foodborne intoxications"),
    ("A06", "Amoebiasis"), ("A07", "Other protozoal intestinal diseases"),
    ("A08", "Viral and other specified intestinal infections"),
    ("A09", "Diarrhoea and gastroenteritis of presumed infectious origin"),
])
_icd_block("I Infectious", "Tuberculosis", [
    ("A15", "Respiratory tuberculosis, bacteriologically and histologically confirmed"),
    ("A16", "Respiratory tuberculosis, not confirmed bacteriologically or histologically"),
    ("A17", "Tuberculosis of nervous system"),
    ("A18", "Tuberculosis of other organs"),
    ("A19", "Miliary tuberculosis"),
])
_icd_block("I Infectious", "Other bacterial", [
    ("A20", "Plague"), ("A21", "Tularaemia"), ("A22", "Anthrax"),
    ("A23", "Brucellosis"), ("A24", "Glanders and melioidosis"),
    ("A25", "Rat-bite fevers"), ("A26", "Erysipeloid"), ("A27", "Leptospirosis"),
    ("A28", "Other zoonotic bacterial diseases NEC"),
    ("A30", "Leprosy [Hansen disease]"), ("A31", "Infection due to other mycobacteria"),
    ("A32", "Listeriosis"), ("A33", "Tetanus neonatorum"),
    ("A34", "Obstetrical tetanus"), ("A35", "Other tetanus"),
    ("A36", "Diphtheria"), ("A37", "Whooping cough"),
    ("A38", "Scarlet fever"), ("A39", "Meningococcal infection"),
    ("A40", "Streptococcal sepsis"), ("A41", "Other sepsis"),
    ("A42", "Actinomycosis"), ("A43", "Nocardiosis"),
    ("A44", "Bartonellosis"), ("A46", "Erysipelas"),
    ("A48", "Other bacterial diseases NEC"),
    ("A49", "Bacterial infection of unspecified site"),
])
_icd_block("I Infectious", "Sexually transmitted", [
    ("A50", "Congenital syphilis"), ("A51", "Early syphilis"),
    ("A52", "Late syphilis"), ("A53", "Other and unspecified syphilis"),
    ("A54", "Gonococcal infection"), ("A55", "Chlamydial lymphogranuloma"),
    ("A56", "Other sexually transmitted chlamydial diseases"),
    ("A57", "Chancroid"), ("A58", "Granuloma inguinale"),
    ("A59", "Trichomoniasis"), ("A60", "Anogenital herpesviral infection"),
    ("A63", "Other predominantly sexually transmitted diseases NEC"),
    ("A64", "Unspecified sexually transmitted disease"),
])
_icd_block("I Infectious", "Other spirochaetal", [
    ("A65", "Nonvenereal syphilis"), ("A66", "Yaws"), ("A67", "Pinta [carate]"),
    ("A68", "Relapsing fevers"), ("A69", "Other spirochaetal infections"),
    ("A70", "Chlamydia psittaci infection"),
    ("A71", "Trachoma"), ("A74", "Other diseases caused by chlamydiae"),
])
_icd_block("I Infectious", "Viral CNS", [
    ("A80", "Acute poliomyelitis"), ("A81", "Atypical virus infections of CNS"),
    ("A82", "Rabies"), ("A83", "Mosquito-borne viral encephalitis"),
    ("A84", "Tick-borne viral encephalitis"),
    ("A85", "Other viral encephalitis NEC"),
    ("A86", "Unspecified viral encephalitis"), ("A87", "Viral meningitis"),
    ("A88", "Other viral infections of CNS NEC"),
    ("A89", "Unspecified viral infection of CNS"),
])
_icd_block("I Infectious", "Arthropod-borne / haemorrhagic", [
    ("A90", "Dengue fever [classical dengue]"), ("A91", "Dengue haemorrhagic fever"),
    ("A92", "Other mosquito-borne viral fevers"),
    ("A93", "Other arthropod-borne viral fevers NEC"),
    ("A94", "Unspecified arthropod-borne viral fever"),
    ("A95", "Yellow fever"), ("A96", "Arenaviral haemorrhagic fever"),
    ("A97", "Dengue"), ("A98", "Other viral haemorrhagic fevers NEC"),
    ("A99", "Unspecified viral haemorrhagic fever"),
])
_icd_block("I Infectious", "Viral skin and mucous membranes", [
    ("B00", "Herpesviral [herpes simplex] infections"),
    ("B01", "Varicella [chickenpox]"), ("B02", "Zoster [herpes zoster]"),
    ("B03", "Smallpox"), ("B04", "Monkeypox"), ("B05", "Measles"),
    ("B06", "Rubella [German measles]"), ("B07", "Viral warts"),
    ("B08", "Other viral infections with skin / mucous lesions NEC"),
    ("B09", "Unspecified viral infection with skin / mucous lesions"),
])
_icd_block("I Infectious", "Viral hepatitis", [
    ("B15", "Acute hepatitis A"), ("B16", "Acute hepatitis B"),
    ("B17", "Other acute viral hepatitis"), ("B18", "Chronic viral hepatitis"),
    ("B19", "Unspecified viral hepatitis"),
])
_icd_block("I Infectious", "HIV", [
    ("B20", "HIV disease resulting in infectious and parasitic diseases"),
    ("B21", "HIV disease resulting in malignant neoplasms"),
    ("B22", "HIV disease resulting in other specified diseases"),
    ("B23", "HIV disease resulting in other conditions"),
    ("B24", "Unspecified HIV disease"),
])
_icd_block("I Infectious", "Other viral and parasitic", [
    ("B25", "Cytomegaloviral disease"), ("B26", "Mumps"),
    ("B27", "Infectious mononucleosis"), ("B30", "Viral conjunctivitis"),
    ("B33", "Other viral diseases NEC"),
    ("B34", "Viral infection of unspecified site"),
    ("B35", "Dermatophytosis"), ("B36", "Other superficial mycoses"),
    ("B37", "Candidiasis"), ("B38", "Coccidioidomycosis"),
    ("B39", "Histoplasmosis"), ("B40", "Blastomycosis"),
    ("B44", "Aspergillosis"),
    ("B45", "Cryptococcosis"), ("B46", "Zygomycosis"),
    ("B48", "Other mycoses NEC"), ("B49", "Unspecified mycosis"),
    ("B50", "Plasmodium falciparum malaria"),
    ("B51", "Plasmodium vivax malaria"),
    ("B52", "Plasmodium malariae malaria"),
    ("B53", "Other parasitologically confirmed malaria"),
    ("B54", "Unspecified malaria"),
    ("B55", "Leishmaniasis"), ("B56", "African trypanosomiasis"),
    ("B57", "Chagas disease"), ("B58", "Toxoplasmosis"),
    ("B59", "Pneumocystosis"), ("B60", "Other protozoal diseases NEC"),
    ("B65", "Schistosomiasis [bilharziasis]"),
    ("B66", "Other fluke infections"), ("B67", "Echinococcosis"),
    ("B68", "Taeniasis"), ("B69", "Cysticercosis"),
    ("B70", "Diphyllobothriasis and sparganosis"),
    ("B71", "Other cestode infections"),
    ("B72", "Dracunculiasis"), ("B73", "Onchocerciasis"),
    ("B74", "Filariasis"), ("B75", "Trichinellosis"),
    ("B76", "Hookworm diseases"), ("B77", "Ascariasis"),
    ("B78", "Strongyloidiasis"), ("B79", "Trichuriasis"),
    ("B80", "Enterobiasis"), ("B81", "Other intestinal helminthiases NEC"),
    ("B82", "Unspecified intestinal parasitism"),
    ("B83", "Other helminthiases"),
    ("B85", "Pediculosis and phthiriasis"), ("B86", "Scabies"),
    ("B87", "Myiasis"), ("B88", "Other infestations"),
    ("B89", "Unspecified parasitic disease"),
    ("B90", "Sequelae of tuberculosis"),
    ("B91", "Sequelae of poliomyelitis"),
    ("B92", "Sequelae of leprosy"),
    ("B94", "Sequelae of other / unspecified infectious / parasitic diseases"),
    ("B95", "Streptococcus and staphylococcus as cause of diseases classified elsewhere"),
    ("B96", "Other bacterial agents as cause of diseases classified elsewhere"),
    ("B97", "Viral agents as the cause of diseases classified elsewhere"),
    ("B99", "Other and unspecified infectious diseases"),
])

# Chapter II — Neoplasms (C00–D48)
_icd_block("II Neoplasms", "Malignant – lip / oral / pharynx", [
    ("C00", "Malignant neoplasm of lip"),
    ("C01", "Malignant neoplasm of base of tongue"),
    ("C02", "Malignant neoplasm of other / unspecified parts of tongue"),
    ("C03", "Malignant neoplasm of gum"),
    ("C04", "Malignant neoplasm of floor of mouth"),
    ("C05", "Malignant neoplasm of palate"),
    ("C06", "Malignant neoplasm of other / unspecified parts of mouth"),
    ("C07", "Malignant neoplasm of parotid gland"),
    ("C08", "Malignant neoplasm of other / unspecified major salivary glands"),
    ("C09", "Malignant neoplasm of tonsil"),
    ("C10", "Malignant neoplasm of oropharynx"),
    ("C11", "Malignant neoplasm of nasopharynx"),
    ("C12", "Malignant neoplasm of pyriform sinus"),
    ("C13", "Malignant neoplasm of hypopharynx"),
    ("C14", "Malignant neoplasm of other / ill-defined sites in lip, oral cavity and pharynx"),
])
_icd_block("II Neoplasms", "Malignant – digestive organs", [
    ("C15", "Malignant neoplasm of oesophagus"),
    ("C16", "Malignant neoplasm of stomach"),
    ("C17", "Malignant neoplasm of small intestine"),
    ("C18", "Malignant neoplasm of colon"),
    ("C19", "Malignant neoplasm of rectosigmoid junction"),
    ("C20", "Malignant neoplasm of rectum"),
    ("C21", "Malignant neoplasm of anus and anal canal"),
    ("C22", "Malignant neoplasm of liver and intrahepatic bile ducts"),
    ("C23", "Malignant neoplasm of gallbladder"),
    ("C24", "Malignant neoplasm of other / unspecified parts of biliary tract"),
    ("C25", "Malignant neoplasm of pancreas"),
    ("C26", "Malignant neoplasm of other / ill-defined digestive organs"),
])
_icd_block("II Neoplasms", "Malignant – respiratory and intrathoracic", [
    ("C30", "Malignant neoplasm of nasal cavity and middle ear"),
    ("C31", "Malignant neoplasm of accessory sinuses"),
    ("C32", "Malignant neoplasm of larynx"),
    ("C33", "Malignant neoplasm of trachea"),
    ("C34", "Malignant neoplasm of bronchus and lung"),
    ("C37", "Malignant neoplasm of thymus"),
    ("C38", "Malignant neoplasm of heart, mediastinum and pleura"),
    ("C39", "Malignant neoplasm of other / ill-defined sites in respiratory system"),
])
_icd_block("II Neoplasms", "Malignant – bone, skin, mesothelial", [
    ("C40", "Malignant neoplasm of bone / articular cartilage of limbs"),
    ("C41", "Malignant neoplasm of bone / articular cartilage of other / unspecified sites"),
    ("C43", "Malignant melanoma of skin"),
    ("C44", "Other malignant neoplasms of skin"),
    ("C45", "Mesothelioma"), ("C46", "Kaposi sarcoma"),
    ("C47", "Malignant neoplasm of peripheral nerves and autonomic nervous system"),
    ("C48", "Malignant neoplasm of retroperitoneum and peritoneum"),
    ("C49", "Malignant neoplasm of other connective and soft tissue"),
])
_icd_block("II Neoplasms", "Malignant – breast / genitourinary", [
    ("C50", "Malignant neoplasm of breast"),
    ("C51", "Malignant neoplasm of vulva"), ("C52", "Malignant neoplasm of vagina"),
    ("C53", "Malignant neoplasm of cervix uteri"),
    ("C54", "Malignant neoplasm of corpus uteri"),
    ("C55", "Malignant neoplasm of uterus, part unspecified"),
    ("C56", "Malignant neoplasm of ovary"),
    ("C57", "Malignant neoplasm of other / unspecified female genital organs"),
    ("C58", "Malignant neoplasm of placenta"),
    ("C60", "Malignant neoplasm of penis"),
    ("C61", "Malignant neoplasm of prostate"),
    ("C62", "Malignant neoplasm of testis"),
    ("C63", "Malignant neoplasm of other / unspecified male genital organs"),
    ("C64", "Malignant neoplasm of kidney, except renal pelvis"),
    ("C65", "Malignant neoplasm of renal pelvis"),
    ("C66", "Malignant neoplasm of ureter"),
    ("C67", "Malignant neoplasm of bladder"),
    ("C68", "Malignant neoplasm of other / unspecified urinary organs"),
])
_icd_block("II Neoplasms", "Malignant – eye / brain / endocrine", [
    ("C69", "Malignant neoplasm of eye and adnexa"),
    ("C70", "Malignant neoplasm of meninges"),
    ("C71", "Malignant neoplasm of brain"),
    ("C72", "Malignant neoplasm of spinal cord, cranial nerves and CNS parts NEC"),
    ("C73", "Malignant neoplasm of thyroid gland"),
    ("C74", "Malignant neoplasm of adrenal gland"),
    ("C75", "Malignant neoplasm of other endocrine glands and related structures"),
    ("C76", "Malignant neoplasm of other / ill-defined sites"),
    ("C77", "Secondary / unspecified malignant neoplasm of lymph nodes"),
    ("C78", "Secondary malignant neoplasm of respiratory and digestive organs"),
    ("C79", "Secondary malignant neoplasm of other / unspecified sites"),
    ("C80", "Malignant neoplasm without specification of site"),
])
_icd_block("II Neoplasms", "Lymphoid and haematopoietic", [
    ("C81", "Hodgkin lymphoma"), ("C82", "Follicular lymphoma"),
    ("C83", "Non-follicular lymphoma"),
    ("C84", "Mature T/NK-cell lymphomas"),
    ("C85", "Other / unspecified types of non-Hodgkin lymphoma"),
    ("C88", "Malignant immunoproliferative diseases"),
    ("C90", "Multiple myeloma and malignant plasma cell neoplasms"),
    ("C91", "Lymphoid leukaemia"), ("C92", "Myeloid leukaemia"),
    ("C93", "Monocytic leukaemia"), ("C94", "Other leukaemias of specified cell type"),
    ("C95", "Leukaemia of unspecified cell type"),
    ("C96", "Other / unspecified malignant neoplasms of lymphoid / haematopoietic / related tissue"),
    ("D00", "Carcinoma in situ of oral cavity, oesophagus and stomach"),
    ("D01", "Carcinoma in situ of other / unspecified digestive organs"),
    ("D02", "Carcinoma in situ of middle ear and respiratory system"),
    ("D03", "Melanoma in situ"),
    ("D04", "Carcinoma in situ of skin"),
    ("D05", "Carcinoma in situ of breast"),
    ("D06", "Carcinoma in situ of cervix uteri"),
    ("D07", "Carcinoma in situ of other / unspecified genital organs"),
    ("D09", "Carcinoma in situ of other / unspecified sites"),
])

# Chapter III — Blood disorders (D50–D89)
_icd_block("III Blood", "Anaemias", [
    ("D50", "Iron deficiency anaemia"),
    ("D51", "Vitamin B12 deficiency anaemia"),
    ("D52", "Folate deficiency anaemia"),
    ("D53", "Other nutritional anaemias"),
    ("D55", "Anaemia due to enzyme disorders"),
    ("D56", "Thalassaemia"),
    ("D57", "Sickle-cell disorders"),
    ("D58", "Other hereditary haemolytic anaemias"),
    ("D59", "Acquired haemolytic anaemia"),
    ("D60", "Acquired pure red cell aplasia [erythroblastopenia]"),
    ("D61", "Other aplastic anaemias"),
    ("D62", "Acute posthaemorrhagic anaemia"),
    ("D63", "Anaemia in chronic diseases classified elsewhere"),
    ("D64", "Other anaemias"),
])
_icd_block("III Blood", "Coagulation defects", [
    ("D65", "Disseminated intravascular coagulation"),
    ("D66", "Hereditary factor VIII deficiency"),
    ("D67", "Hereditary factor IX deficiency"),
    ("D68", "Other coagulation defects"),
    ("D69", "Purpura and other haemorrhagic conditions"),
])
_icd_block("III Blood", "WBC and other", [
    ("D70", "Agranulocytosis"),
    ("D71", "Functional disorders of polymorphonuclear neutrophils"),
    ("D72", "Other disorders of white blood cells"),
    ("D73", "Diseases of spleen"),
    ("D74", "Methaemoglobinaemia"),
    ("D75", "Other / unspecified diseases of blood and blood-forming organs"),
    ("D76", "Other specified diseases with lymphoreticular / reticulohistiocytic tissue"),
    ("D77", "Other disorders of blood / blood-forming organs in diseases classified elsewhere"),
])

# Chapter IV — Endocrine (E00–E90)
_icd_block("IV Endocrine", "Diabetes", [
    ("E10", "Type 1 diabetes mellitus"),
    ("E11", "Type 2 diabetes mellitus"),
    ("E12", "Malnutrition-related diabetes mellitus"),
    ("E13", "Other specified diabetes mellitus"),
    ("E14", "Unspecified diabetes mellitus"),
    ("E15", "Nondiabetic hypoglycaemic coma"),
    ("E16", "Other disorders of pancreatic internal secretion"),
])
_icd_block("IV Endocrine", "Thyroid", [
    ("E00", "Congenital iodine-deficiency syndrome"),
    ("E01", "Iodine-deficiency-related thyroid disorders and allied conditions"),
    ("E02", "Subclinical iodine-deficiency hypothyroidism"),
    ("E03", "Other hypothyroidism"),
    ("E04", "Other nontoxic goitre"),
    ("E05", "Thyrotoxicosis [hyperthyroidism]"),
    ("E06", "Thyroiditis"), ("E07", "Other disorders of thyroid"),
])
_icd_block("IV Endocrine", "Other endocrine / metabolic", [
    ("E20", "Hypoparathyroidism"), ("E21", "Hyperparathyroidism and other disorders of parathyroid"),
    ("E22", "Hyperfunction of pituitary gland"),
    ("E23", "Hypofunction and other disorders of pituitary gland"),
    ("E24", "Cushing syndrome"),
    ("E25", "Adrenogenital disorders"),
    ("E26", "Hyperaldosteronism"), ("E27", "Other disorders of adrenal gland"),
    ("E28", "Ovarian dysfunction"), ("E29", "Testicular dysfunction"),
    ("E30", "Disorders of puberty NEC"),
    ("E31", "Polyglandular dysfunction"),
    ("E40", "Kwashiorkor"), ("E41", "Nutritional marasmus"),
    ("E43", "Unspecified severe protein-energy malnutrition"),
    ("E44", "Protein-energy malnutrition of moderate / mild degree"),
    ("E50", "Vitamin A deficiency"),
    ("E51", "Thiamine deficiency"), ("E52", "Niacin deficiency [pellagra]"),
    ("E53", "Deficiency of other B group vitamins"),
    ("E54", "Ascorbic acid deficiency"), ("E55", "Vitamin D deficiency"),
    ("E56", "Other vitamin deficiencies"),
    ("E58", "Dietary calcium deficiency"),
    ("E61", "Deficiency of other nutrient elements"),
    ("E63", "Other nutritional deficiencies"),
    ("E64", "Sequelae of malnutrition and other nutritional deficiencies"),
    ("E65", "Localized adiposity"),
    ("E66", "Obesity"), ("E67", "Other hyperalimentation"),
    ("E70", "Disorders of aromatic amino-acid metabolism"),
    ("E71", "Disorders of branched-chain amino-acid metabolism / fatty-acid metabolism"),
    ("E72", "Other disorders of amino-acid metabolism"),
    ("E73", "Lactose intolerance"),
    ("E74", "Other disorders of carbohydrate metabolism"),
    ("E75", "Disorders of sphingolipid metabolism and other lipid storage disorders"),
    ("E76", "Disorders of glycosaminoglycan metabolism"),
    ("E77", "Disorders of glycoprotein metabolism"),
    ("E78", "Disorders of lipoprotein metabolism and other lipidaemias"),
    ("E80", "Disorders of porphyrin and bilirubin metabolism"),
    ("E83", "Disorders of mineral metabolism"),
    ("E84", "Cystic fibrosis"),
    ("E85", "Amyloidosis"),
    ("E86", "Volume depletion"),
    ("E87", "Other disorders of fluid, electrolyte and acid-base balance"),
    ("E88", "Other metabolic disorders"),
    ("E89", "Postprocedural endocrine and metabolic disorders NEC"),
])

# Chapter V — Mental and behavioural (F00–F99)
_icd_block("V Mental", "Organic / substance", [
    ("F00", "Dementia in Alzheimer disease"), ("F01", "Vascular dementia"),
    ("F02", "Dementia in other diseases classified elsewhere"),
    ("F03", "Unspecified dementia"),
    ("F04", "Organic amnesic syndrome"),
    ("F05", "Delirium not induced by alcohol / psychoactive substances"),
    ("F06", "Other mental disorders due to brain damage / physical disease"),
    ("F07", "Personality / behavioural disorders due to brain disease"),
    ("F09", "Unspecified organic / symptomatic mental disorder"),
    ("F10", "Mental and behavioural disorders due to use of alcohol"),
    ("F11", "Mental and behavioural disorders due to use of opioids"),
    ("F12", "Mental and behavioural disorders due to use of cannabinoids"),
    ("F13", "Mental and behavioural disorders due to use of sedatives or hypnotics"),
    ("F14", "Mental and behavioural disorders due to use of cocaine"),
    ("F15", "Mental and behavioural disorders due to use of other stimulants"),
    ("F16", "Mental and behavioural disorders due to use of hallucinogens"),
    ("F17", "Mental and behavioural disorders due to use of tobacco"),
    ("F19", "Mental and behavioural disorders due to multiple drug use"),
])
_icd_block("V Mental", "Schizophrenia and mood", [
    ("F20", "Schizophrenia"), ("F21", "Schizotypal disorder"),
    ("F22", "Persistent delusional disorders"),
    ("F23", "Acute and transient psychotic disorders"),
    ("F25", "Schizoaffective disorders"),
    ("F30", "Manic episode"), ("F31", "Bipolar affective disorder"),
    ("F32", "Depressive episode"), ("F33", "Recurrent depressive disorder"),
    ("F34", "Persistent mood [affective] disorders"),
    ("F40", "Phobic anxiety disorders"), ("F41", "Other anxiety disorders"),
    ("F42", "Obsessive-compulsive disorder"),
    ("F43", "Reaction to severe stress, and adjustment disorders"),
    ("F44", "Dissociative [conversion] disorders"),
    ("F45", "Somatoform disorders"),
    ("F50", "Eating disorders"), ("F51", "Nonorganic sleep disorders"),
    ("F52", "Sexual dysfunction"),
    ("F60", "Specific personality disorders"),
    ("F70", "Mild mental retardation"), ("F71", "Moderate mental retardation"),
    ("F72", "Severe mental retardation"), ("F73", "Profound mental retardation"),
    ("F80", "Specific developmental disorders of speech and language"),
    ("F81", "Specific developmental disorders of scholastic skills"),
    ("F84", "Pervasive developmental disorders"),
    ("F90", "Hyperkinetic disorders"),
    ("F91", "Conduct disorders"),
    ("F95", "Tic disorders"),
    ("F99", "Mental disorder, not otherwise specified"),
])

# Chapter VI — Nervous system (G00–G99)
_icd_block("VI Nervous", "CNS inflammatory", [
    ("G00", "Bacterial meningitis NEC"), ("G01", "Meningitis in bacterial diseases classified elsewhere"),
    ("G02", "Meningitis in other infectious / parasitic diseases classified elsewhere"),
    ("G03", "Meningitis due to other / unspecified causes"),
    ("G04", "Encephalitis, myelitis and encephalomyelitis"),
    ("G06", "Intracranial and intraspinal abscess and granuloma"),
    ("G08", "Intracranial / intraspinal phlebitis and thrombophlebitis"),
])
_icd_block("VI Nervous", "Degenerative / demyelinating", [
    ("G20", "Parkinson disease"), ("G21", "Secondary parkinsonism"),
    ("G23", "Other degenerative diseases of basal ganglia"),
    ("G24", "Dystonia"), ("G25", "Other extrapyramidal and movement disorders"),
    ("G30", "Alzheimer disease"), ("G31", "Other degenerative diseases of nervous system NEC"),
    ("G35", "Multiple sclerosis"), ("G36", "Other acute disseminated demyelination"),
    ("G37", "Other demyelinating diseases of CNS"),
])
_icd_block("VI Nervous", "Episodic / peripheral / muscle", [
    ("G40", "Epilepsy"), ("G41", "Status epilepticus"),
    ("G43", "Migraine"), ("G44", "Other headache syndromes"),
    ("G45", "Transient cerebral ischaemic attacks and related syndromes"),
    ("G46", "Vascular syndromes of brain in cerebrovascular diseases"),
    ("G47", "Sleep disorders"),
    ("G50", "Disorders of trigeminal nerve"),
    ("G51", "Facial nerve disorders"),
    ("G52", "Disorders of other cranial nerves"),
    ("G54", "Nerve root and plexus disorders"),
    ("G56", "Mononeuropathies of upper limb"),
    ("G57", "Mononeuropathies of lower limb"),
    ("G60", "Hereditary and idiopathic neuropathy"),
    ("G61", "Inflammatory polyneuropathy"),
    ("G62", "Other polyneuropathies"),
    ("G70", "Myasthenia gravis and other myoneural disorders"),
    ("G71", "Primary disorders of muscles"),
    ("G80", "Cerebral palsy"), ("G81", "Hemiplegia"),
    ("G82", "Paraplegia and tetraplegia"),
    ("G83", "Other paralytic syndromes"),
    ("G90", "Disorders of autonomic nervous system"),
    ("G91", "Hydrocephalus"),
    ("G93", "Other disorders of brain"),
    ("G95", "Other diseases of spinal cord"),
    ("G99", "Other disorders of nervous system in diseases classified elsewhere"),
])

# Chapter VII — Eye (H00–H59)
_icd_block("VII Eye", "Adnexa / sclera / cornea / lens", [
    ("H00", "Hordeolum and chalazion"), ("H01", "Other inflammation of eyelid"),
    ("H02", "Other disorders of eyelid"),
    ("H04", "Disorders of lacrimal system"),
    ("H05", "Disorders of orbit"),
    ("H10", "Conjunctivitis"), ("H11", "Other disorders of conjunctiva"),
    ("H15", "Disorders of sclera"), ("H16", "Keratitis"),
    ("H17", "Corneal scars and opacities"),
    ("H18", "Other disorders of cornea"),
    ("H20", "Iridocyclitis"), ("H21", "Other disorders of iris and ciliary body"),
    ("H25", "Senile cataract"), ("H26", "Other cataract"),
    ("H27", "Other disorders of lens"),
])
_icd_block("VII Eye", "Retina / glaucoma / refraction", [
    ("H30", "Chorioretinal inflammation"),
    ("H33", "Retinal detachments and breaks"),
    ("H34", "Retinal vascular occlusions"),
    ("H35", "Other retinal disorders"),
    ("H36", "Retinal disorders in diseases classified elsewhere"),
    ("H40", "Glaucoma"), ("H43", "Disorders of vitreous body"),
    ("H44", "Disorders of globe"),
    ("H46", "Optic neuritis"),
    ("H47", "Other disorders of optic [2nd] nerve and visual pathways"),
    ("H49", "Paralytic strabismus"), ("H50", "Other strabismus"),
    ("H52", "Disorders of refraction and accommodation"),
    ("H53", "Visual disturbances"),
    ("H54", "Blindness and low vision"),
])

# Chapter VIII — Ear (H60–H95)
_icd_block("VIII Ear", "External / middle / inner", [
    ("H60", "Otitis externa"),
    ("H65", "Nonsuppurative otitis media"),
    ("H66", "Suppurative and unspecified otitis media"),
    ("H68", "Eustachian salpingitis and obstruction"),
    ("H70", "Mastoiditis and related conditions"),
    ("H80", "Otosclerosis"),
    ("H81", "Disorders of vestibular function"),
    ("H83", "Other diseases of inner ear"),
    ("H90", "Conductive and sensorineural hearing loss"),
    ("H91", "Other hearing loss"),
    ("H92", "Otalgia and effusion of ear"),
    ("H93", "Other disorders of ear NEC"),
])

# Chapter IX — Circulatory (I00–I99)
_icd_block("IX Circulatory", "Rheumatic / hypertensive / ischaemic", [
    ("I00", "Rheumatic fever without mention of heart involvement"),
    ("I01", "Rheumatic fever with heart involvement"),
    ("I05", "Rheumatic mitral valve diseases"),
    ("I06", "Rheumatic aortic valve diseases"),
    ("I07", "Rheumatic tricuspid valve diseases"),
    ("I08", "Multiple valve diseases"),
    ("I10", "Essential (primary) hypertension"),
    ("I11", "Hypertensive heart disease"),
    ("I12", "Hypertensive renal disease"),
    ("I13", "Hypertensive heart and renal disease"),
    ("I15", "Secondary hypertension"),
    ("I20", "Angina pectoris"),
    ("I21", "Acute myocardial infarction"),
    ("I22", "Subsequent myocardial infarction"),
    ("I24", "Other acute ischaemic heart diseases"),
    ("I25", "Chronic ischaemic heart disease"),
])
_icd_block("IX Circulatory", "Pulmonary / pericardial / endocardial / myocardial", [
    ("I26", "Pulmonary embolism"), ("I27", "Other pulmonary heart diseases"),
    ("I30", "Acute pericarditis"), ("I31", "Other diseases of pericardium"),
    ("I33", "Acute and subacute endocarditis"),
    ("I34", "Nonrheumatic mitral valve disorders"),
    ("I35", "Nonrheumatic aortic valve disorders"),
    ("I36", "Nonrheumatic tricuspid valve disorders"),
    ("I37", "Pulmonary valve disorders"),
    ("I40", "Acute myocarditis"), ("I42", "Cardiomyopathy"),
    ("I44", "Atrioventricular and left bundle-branch block"),
    ("I45", "Other conduction disorders"),
    ("I46", "Cardiac arrest"),
    ("I47", "Paroxysmal tachycardia"),
    ("I48", "Atrial fibrillation and flutter"),
    ("I49", "Other cardiac arrhythmias"),
    ("I50", "Heart failure"),
    ("I51", "Complications / ill-defined descriptions of heart disease"),
])
_icd_block("IX Circulatory", "Cerebrovascular / arterial / venous", [
    ("I60", "Subarachnoid haemorrhage"),
    ("I61", "Intracerebral haemorrhage"),
    ("I62", "Other nontraumatic intracranial haemorrhage"),
    ("I63", "Cerebral infarction"),
    ("I64", "Stroke, not specified as haemorrhage or infarction"),
    ("I65", "Occlusion and stenosis of precerebral arteries"),
    ("I67", "Other cerebrovascular diseases"),
    ("I69", "Sequelae of cerebrovascular disease"),
    ("I70", "Atherosclerosis"),
    ("I71", "Aortic aneurysm and dissection"),
    ("I72", "Other aneurysm"), ("I73", "Other peripheral vascular diseases"),
    ("I74", "Arterial embolism and thrombosis"),
    ("I80", "Phlebitis and thrombophlebitis"),
    ("I82", "Other venous embolism and thrombosis"),
    ("I83", "Varicose veins of lower extremities"),
    ("I84", "Haemorrhoids"),
    ("I85", "Oesophageal varices"),
    ("I86", "Varicose veins of other sites"),
    ("I87", "Other disorders of veins"),
    ("I88", "Nonspecific lymphadenitis"),
    ("I89", "Other noninfective disorders of lymphatic vessels and lymph nodes"),
    ("I95", "Hypotension"),
    ("I99", "Other and unspecified disorders of circulatory system"),
])

# Chapter X — Respiratory (J00–J99)
_icd_block("X Respiratory", "Acute upper", [
    ("J00", "Acute nasopharyngitis [common cold]"),
    ("J01", "Acute sinusitis"), ("J02", "Acute pharyngitis"),
    ("J03", "Acute tonsillitis"), ("J04", "Acute laryngitis and tracheitis"),
    ("J05", "Acute obstructive laryngitis [croup] and epiglottitis"),
    ("J06", "Acute upper respiratory infections of multiple / unspecified sites"),
])
_icd_block("X Respiratory", "Influenza / pneumonia / lower acute", [
    ("J09", "Influenza due to identified zoonotic / pandemic strain"),
    ("J10", "Influenza due to identified seasonal influenza virus"),
    ("J11", "Influenza, virus not identified"),
    ("J12", "Viral pneumonia NEC"),
    ("J13", "Pneumonia due to Streptococcus pneumoniae"),
    ("J14", "Pneumonia due to Haemophilus influenzae"),
    ("J15", "Bacterial pneumonia NEC"),
    ("J16", "Pneumonia due to other infectious organisms NEC"),
    ("J17", "Pneumonia in diseases classified elsewhere"),
    ("J18", "Pneumonia, organism unspecified"),
    ("J20", "Acute bronchitis"),
    ("J21", "Acute bronchiolitis"),
    ("J22", "Unspecified acute lower respiratory infection"),
])
_icd_block("X Respiratory", "Chronic lower / obstructive", [
    ("J30", "Vasomotor and allergic rhinitis"),
    ("J31", "Chronic rhinitis, nasopharyngitis and pharyngitis"),
    ("J32", "Chronic sinusitis"),
    ("J35", "Chronic diseases of tonsils and adenoids"),
    ("J40", "Bronchitis, not specified as acute or chronic"),
    ("J41", "Simple and mucopurulent chronic bronchitis"),
    ("J42", "Unspecified chronic bronchitis"),
    ("J43", "Emphysema"),
    ("J44", "Other chronic obstructive pulmonary disease"),
    ("J45", "Asthma"), ("J46", "Status asthmaticus"),
    ("J47", "Bronchiectasis"),
    ("J60", "Coalworker pneumoconiosis"),
    ("J61", "Pneumoconiosis due to asbestos and other mineral fibres"),
    ("J62", "Pneumoconiosis due to dust containing silica"),
    ("J63", "Pneumoconiosis due to other inorganic dusts"),
    ("J67", "Hypersensitivity pneumonitis due to organic dust"),
    ("J68", "Respiratory conditions due to inhalation of chemicals, gases, fumes and vapours"),
    ("J80", "Adult respiratory distress syndrome"),
    ("J81", "Pulmonary oedema"),
    ("J84", "Other interstitial pulmonary diseases"),
    ("J85", "Abscess of lung and mediastinum"),
    ("J86", "Pyothorax"),
    ("J90", "Pleural effusion NEC"),
    ("J91", "Pleural effusion in conditions classified elsewhere"),
    ("J93", "Pneumothorax"),
    ("J94", "Other pleural conditions"),
    ("J96", "Respiratory failure NEC"),
    ("J98", "Other respiratory disorders"),
])

# Chapter XI — Digestive (K00–K93)
_icd_block("XI Digestive", "Oral / oesophagus / stomach / duodenum", [
    ("K00", "Disorders of tooth development and eruption"),
    ("K02", "Dental caries"),
    ("K04", "Diseases of pulp and periapical tissues"),
    ("K05", "Gingivitis and periodontal diseases"),
    ("K07", "Dentofacial anomalies including malocclusion"),
    ("K11", "Diseases of salivary glands"),
    ("K12", "Stomatitis and related lesions"),
    ("K13", "Other diseases of lip and oral mucosa"),
    ("K14", "Diseases of tongue"),
    ("K20", "Oesophagitis"), ("K21", "Gastro-oesophageal reflux disease"),
    ("K22", "Other diseases of oesophagus"),
    ("K25", "Gastric ulcer"), ("K26", "Duodenal ulcer"),
    ("K27", "Peptic ulcer, site unspecified"),
    ("K28", "Gastrojejunal ulcer"),
    ("K29", "Gastritis and duodenitis"), ("K30", "Functional dyspepsia"),
])
_icd_block("XI Digestive", "Bowel / hernias / IBD", [
    ("K35", "Acute appendicitis"),
    ("K36", "Other appendicitis"), ("K37", "Unspecified appendicitis"),
    ("K38", "Other diseases of appendix"),
    ("K40", "Inguinal hernia"), ("K41", "Femoral hernia"),
    ("K42", "Umbilical hernia"), ("K43", "Ventral hernia"),
    ("K44", "Diaphragmatic hernia"),
    ("K50", "Crohn disease [regional enteritis]"),
    ("K51", "Ulcerative colitis"),
    ("K52", "Other and unspecified noninfective gastroenteritis and colitis"),
    ("K55", "Vascular disorders of intestine"),
    ("K56", "Paralytic ileus and intestinal obstruction without hernia"),
    ("K57", "Diverticular disease of intestine"),
    ("K58", "Irritable bowel syndrome"),
    ("K59", "Other functional intestinal disorders"),
    ("K60", "Fissure and fistula of anal and rectal regions"),
    ("K61", "Abscess of anal and rectal regions"),
    ("K62", "Other diseases of anus and rectum"),
    ("K63", "Other diseases of intestine"),
    ("K64", "Haemorrhoids and perianal venous thrombosis"),
    ("K65", "Peritonitis"), ("K66", "Other disorders of peritoneum"),
])
_icd_block("XI Digestive", "Liver / gallbladder / pancreas", [
    ("K70", "Alcoholic liver disease"),
    ("K71", "Toxic liver disease"),
    ("K72", "Hepatic failure NEC"),
    ("K73", "Chronic hepatitis NEC"),
    ("K74", "Fibrosis and cirrhosis of liver"),
    ("K75", "Other inflammatory liver diseases"),
    ("K76", "Other diseases of liver"),
    ("K80", "Cholelithiasis"), ("K81", "Cholecystitis"),
    ("K82", "Other diseases of gallbladder"),
    ("K83", "Other diseases of biliary tract"),
    ("K85", "Acute pancreatitis"),
    ("K86", "Other diseases of pancreas"),
    ("K90", "Intestinal malabsorption"),
    ("K91", "Postprocedural digestive disorders NEC"),
    ("K92", "Other diseases of digestive system"),
])

# Chapter XII — Skin (L00–L99)
_icd_block("XII Skin", "Skin and subcutaneous", [
    ("L00", "Staphylococcal scalded skin syndrome"),
    ("L01", "Impetigo"), ("L02", "Cutaneous abscess, furuncle and carbuncle"),
    ("L03", "Cellulitis"),
    ("L08", "Other local infections of skin and subcutaneous tissue"),
    ("L10", "Pemphigus"), ("L12", "Pemphigoid"),
    ("L20", "Atopic dermatitis"), ("L21", "Seborrhoeic dermatitis"),
    ("L22", "Diaper dermatitis"), ("L23", "Allergic contact dermatitis"),
    ("L24", "Irritant contact dermatitis"),
    ("L25", "Unspecified contact dermatitis"),
    ("L27", "Dermatitis due to substances taken internally"),
    ("L28", "Lichen simplex chronicus and prurigo"),
    ("L29", "Pruritus"),
    ("L30", "Other dermatitis"),
    ("L40", "Psoriasis"),
    ("L43", "Lichen planus"), ("L50", "Urticaria"),
    ("L51", "Erythema multiforme"),
    ("L53", "Other erythematous conditions"),
    ("L55", "Sunburn"), ("L56", "Other acute skin changes due to ultraviolet radiation"),
    ("L60", "Nail disorders"),
    ("L63", "Alopecia areata"),
    ("L65", "Other nonscarring hair loss"),
    ("L70", "Acne"), ("L71", "Rosacea"),
    ("L73", "Other follicular disorders"),
    ("L80", "Vitiligo"),
    ("L81", "Other disorders of pigmentation"),
    ("L82", "Seborrhoeic keratosis"),
    ("L83", "Acanthosis nigricans"),
    ("L84", "Corns and callosities"),
    ("L85", "Other epidermal thickening"),
    ("L89", "Decubitus ulcer and pressure area"),
    ("L90", "Atrophic disorders of skin"),
    ("L92", "Granulomatous disorders of skin and subcutaneous tissue"),
    ("L93", "Lupus erythematosus"),
    ("L94", "Other localized connective tissue disorders"),
    ("L98", "Other disorders of skin and subcutaneous tissue NEC"),
])

# Chapter XIII — Musculoskeletal (M00–M99)
_icd_block("XIII Musculoskeletal", "Arthropathies", [
    ("M00", "Pyogenic arthritis"), ("M02", "Reactive arthropathies"),
    ("M05", "Seropositive rheumatoid arthritis"),
    ("M06", "Other rheumatoid arthritis"),
    ("M07", "Psoriatic and enteropathic arthropathies"),
    ("M08", "Juvenile arthritis"),
    ("M10", "Gout"), ("M11", "Other crystal arthropathies"),
    ("M13", "Other arthritis"),
    ("M15", "Polyarthrosis"),
    ("M16", "Coxarthrosis [arthrosis of hip]"),
    ("M17", "Gonarthrosis [arthrosis of knee]"),
    ("M18", "Arthrosis of first carpometacarpal joint"),
    ("M19", "Other arthrosis"),
])
_icd_block("XIII Musculoskeletal", "Connective tissue / dorsopathies / soft tissue / bone", [
    ("M30", "Polyarteritis nodosa and related conditions"),
    ("M31", "Other necrotizing vasculopathies"),
    ("M32", "Systemic lupus erythematosus"),
    ("M33", "Dermatopolymyositis"),
    ("M34", "Systemic sclerosis"),
    ("M35", "Other systemic involvement of connective tissue"),
    ("M40", "Kyphosis and lordosis"),
    ("M41", "Scoliosis"), ("M42", "Spinal osteochondrosis"),
    ("M43", "Other deforming dorsopathies"),
    ("M45", "Ankylosing spondylitis"),
    ("M46", "Other inflammatory spondylopathies"),
    ("M47", "Spondylosis"), ("M48", "Other spondylopathies"),
    ("M50", "Cervical disc disorders"),
    ("M51", "Other intervertebral disc disorders"),
    ("M53", "Other dorsopathies NEC"),
    ("M54", "Dorsalgia"),
    ("M60", "Myositis"), ("M62", "Other disorders of muscle"),
    ("M65", "Synovitis and tenosynovitis"),
    ("M70", "Soft tissue disorders related to use, overuse and pressure"),
    ("M75", "Shoulder lesions"),
    ("M77", "Other enthesopathies"),
    ("M79", "Other soft tissue disorders NEC"),
    ("M80", "Osteoporosis with pathological fracture"),
    ("M81", "Osteoporosis without pathological fracture"),
    ("M83", "Adult osteomalacia"),
    ("M84", "Disorders of continuity of bone"),
    ("M85", "Other disorders of bone density and structure"),
    ("M86", "Osteomyelitis"),
    ("M87", "Osteonecrosis"),
    ("M89", "Other disorders of bone"),
    ("M93", "Other osteochondropathies"),
    ("M94", "Other disorders of cartilage"),
    ("M95", "Other acquired deformities of musculoskeletal system"),
])

# Chapter XIV — Genitourinary (N00–N99)
_icd_block("XIV Genitourinary", "Renal / urinary", [
    ("N00", "Acute nephritic syndrome"), ("N01", "Rapidly progressive nephritic syndrome"),
    ("N02", "Recurrent and persistent haematuria"),
    ("N03", "Chronic nephritic syndrome"),
    ("N04", "Nephrotic syndrome"),
    ("N05", "Unspecified nephritic syndrome"),
    ("N10", "Acute tubulo-interstitial nephritis"),
    ("N11", "Chronic tubulo-interstitial nephritis"),
    ("N12", "Tubulo-interstitial nephritis NEC"),
    ("N13", "Obstructive and reflux uropathy"),
    ("N14", "Drug- and heavy-metal-induced tubulo-interstitial / tubular conditions"),
    ("N15", "Other renal tubulo-interstitial diseases"),
    ("N17", "Acute renal failure"), ("N18", "Chronic kidney disease"),
    ("N19", "Unspecified kidney failure"),
    ("N20", "Calculus of kidney and ureter"),
    ("N21", "Calculus of lower urinary tract"),
    ("N23", "Unspecified renal colic"),
    ("N25", "Disorders resulting from impaired renal tubular function"),
    ("N28", "Other disorders of kidney and ureter NEC"),
    ("N30", "Cystitis"), ("N31", "Neuromuscular dysfunction of bladder"),
    ("N32", "Other disorders of bladder"),
    ("N34", "Urethritis and urethral syndrome"),
    ("N35", "Urethral stricture"),
    ("N36", "Other disorders of urethra"),
    ("N39", "Other disorders of urinary system"),
])
_icd_block("XIV Genitourinary", "Male and female reproductive", [
    ("N40", "Hyperplasia of prostate"),
    ("N41", "Inflammatory diseases of prostate"),
    ("N42", "Other disorders of prostate"),
    ("N43", "Hydrocele and spermatocele"),
    ("N45", "Orchitis and epididymitis"),
    ("N46", "Male infertility"),
    ("N47", "Redundant prepuce, phimosis and paraphimosis"),
    ("N50", "Other disorders of male genital organs"),
    ("N60", "Benign mammary dysplasia"),
    ("N61", "Inflammatory disorders of breast"),
    ("N63", "Unspecified lump in breast"),
    ("N64", "Other disorders of breast"),
    ("N70", "Salpingitis and oophoritis"),
    ("N71", "Inflammatory disease of uterus, except cervix"),
    ("N72", "Inflammatory disease of cervix uteri"),
    ("N73", "Other female pelvic inflammatory diseases"),
    ("N75", "Diseases of Bartholin gland"),
    ("N76", "Other inflammation of vagina and vulva"),
    ("N80", "Endometriosis"),
    ("N81", "Female genital prolapse"),
    ("N83", "Noninflammatory disorders of ovary, fallopian tube and broad ligament"),
    ("N84", "Polyp of female genital tract"),
    ("N85", "Other noninflammatory disorders of uterus, except cervix"),
    ("N86", "Erosion and ectropion of cervix uteri"),
    ("N87", "Dysplasia of cervix uteri"),
    ("N88", "Other noninflammatory disorders of cervix uteri"),
    ("N90", "Other noninflammatory disorders of vulva and perineum"),
    ("N91", "Absent, scanty and rare menstruation"),
    ("N92", "Excessive, frequent and irregular menstruation"),
    ("N93", "Other abnormal uterine and vaginal bleeding"),
    ("N94", "Pain and other conditions associated with female genital organs"),
    ("N95", "Menopausal and other perimenopausal disorders"),
    ("N97", "Female infertility"),
])

# Chapter XV-XVII trimmed selectively
_icd_block("XV Pregnancy", "Pregnancy / delivery / puerperium", [
    ("O00", "Ectopic pregnancy"),
    ("O01", "Hydatidiform mole"),
    ("O02", "Other abnormal products of conception"),
    ("O03", "Spontaneous abortion"),
    ("O04", "Medical abortion"),
    ("O10", "Pre-existing hypertension complicating pregnancy, childbirth and the puerperium"),
    ("O11", "Pre-existing hypertensive disorder with superimposed proteinuria"),
    ("O13", "Gestational [pregnancy-induced] hypertension without significant proteinuria"),
    ("O14", "Pre-eclampsia"),
    ("O15", "Eclampsia"),
    ("O20", "Haemorrhage in early pregnancy"),
    ("O24", "Diabetes mellitus in pregnancy"),
    ("O30", "Multiple gestation"),
    ("O36", "Maternal care for other known / suspected fetal problems"),
    ("O42", "Premature rupture of membranes"),
    ("O60", "Preterm labour and delivery"),
    ("O68", "Labour and delivery complicated by fetal stress"),
    ("O80", "Single spontaneous delivery"),
    ("O82", "Single delivery by caesarean section"),
    ("O88", "Obstetric embolism"),
    ("O90", "Complications of the puerperium NEC"),
])
_icd_block("XVI Perinatal", "Conditions originating in the perinatal period", [
    ("P00", "Fetus and newborn affected by maternal conditions"),
    ("P05", "Slow fetal growth and fetal malnutrition"),
    ("P07", "Disorders related to short gestation and low birth weight NEC"),
    ("P22", "Respiratory distress of newborn"),
    ("P24", "Neonatal aspiration syndromes"),
    ("P36", "Bacterial sepsis of newborn"),
    ("P55", "Haemolytic disease of fetus and newborn"),
    ("P59", "Neonatal jaundice from other and unspecified causes"),
    ("P70", "Transitory disorders of carbohydrate metabolism specific to fetus and newborn"),
])
_icd_block("XVII Congenital", "Congenital malformations / deformations / chromosomal", [
    ("Q00", "Anencephaly and similar malformations"),
    ("Q02", "Microcephaly"),
    ("Q05", "Spina bifida"),
    ("Q20", "Congenital malformations of cardiac chambers and connections"),
    ("Q21", "Congenital malformations of cardiac septa"),
    ("Q23", "Congenital malformations of aortic and mitral valves"),
    ("Q35", "Cleft palate"), ("Q36", "Cleft lip"),
    ("Q37", "Cleft palate with cleft lip"),
    ("Q39", "Congenital malformations of oesophagus"),
    ("Q42", "Congenital absence, atresia and stenosis of large intestine"),
    ("Q43", "Other congenital malformations of intestine"),
    ("Q51", "Congenital malformations of uterus and cervix"),
    ("Q53", "Undescended testicle"),
    ("Q60", "Renal agenesis and other reduction defects of kidney"),
    ("Q66", "Congenital deformities of feet"),
    ("Q70", "Syndactyly"),
    ("Q79", "Congenital malformations of musculoskeletal system NEC"),
    ("Q90", "Down syndrome"),
    ("Q91", "Edwards syndrome and Patau syndrome"),
    ("Q96", "Turner syndrome"),
    ("Q98", "Other sex chromosome abnormalities, male phenotype NEC"),
])

# Chapter XVIII Symptoms and signs (R00–R99) — keep highly clinical ones
_icd_block("XVIII Symptoms", "Cardiovascular / respiratory / GI / GU / neuro signs", [
    ("R00", "Abnormalities of heart beat"), ("R01", "Cardiac murmurs and other cardiac sounds"),
    ("R03", "Abnormal blood pressure reading, without diagnosis"),
    ("R04", "Haemorrhage from respiratory passages"),
    ("R05", "Cough"), ("R06", "Abnormalities of breathing"),
    ("R07", "Pain in throat and chest"),
    ("R09", "Other symptoms and signs involving the circulatory and respiratory systems"),
    ("R10", "Abdominal and pelvic pain"),
    ("R11", "Nausea and vomiting"),
    ("R12", "Heartburn"), ("R13", "Dysphagia"),
    ("R14", "Flatulence and related conditions"),
    ("R15", "Faecal incontinence"),
    ("R16", "Hepatomegaly and splenomegaly NEC"),
    ("R17", "Unspecified jaundice"),
    ("R18", "Ascites"),
    ("R19", "Other symptoms and signs involving the digestive system and abdomen"),
    ("R20", "Disturbances of skin sensation"),
    ("R21", "Rash and other nonspecific skin eruption"),
    ("R22", "Localized swelling, mass and lump of skin and subcutaneous tissue"),
    ("R25", "Abnormal involuntary movements"),
    ("R26", "Abnormalities of gait and mobility"),
    ("R29", "Other symptoms and signs involving the nervous and musculoskeletal systems"),
    ("R30", "Pain associated with micturition"),
    ("R31", "Unspecified haematuria"),
    ("R32", "Unspecified urinary incontinence"),
    ("R33", "Retention of urine"),
    ("R34", "Anuria and oliguria"),
    ("R35", "Polyuria"), ("R39", "Other symptoms and signs involving the urinary system"),
    ("R40", "Somnolence, stupor and coma"),
    ("R41", "Other symptoms and signs involving cognitive functions and awareness"),
    ("R42", "Dizziness and giddiness"),
    ("R45", "Symptoms and signs involving emotional state"),
    ("R47", "Speech disturbances NEC"),
    ("R50", "Fever of other and unknown origin"),
    ("R51", "Headache"), ("R52", "Pain, not elsewhere classified"),
    ("R53", "Malaise and fatigue"),
    ("R55", "Syncope and collapse"),
    ("R56", "Convulsions, not elsewhere classified"),
    ("R57", "Shock NEC"),
    ("R58", "Haemorrhage NEC"), ("R59", "Enlarged lymph nodes"),
    ("R60", "Oedema NEC"),
    ("R63", "Symptoms and signs concerning food and fluid intake"),
    ("R64", "Cachexia"),
    ("R65", "Symptoms and signs specifically associated with systemic inflammation and infection"),
    ("R70", "Elevated erythrocyte sedimentation rate / abnormal viscosity"),
    ("R71", "Abnormality of red blood cells"),
    ("R73", "Elevated blood glucose level"),
    ("R74", "Abnormal serum enzyme levels"),
    ("R75", "Laboratory evidence of HIV"),
    ("R76", "Other abnormal immunological findings in serum"),
    ("R77", "Other abnormalities of plasma proteins"),
    ("R78", "Findings of drugs and other substances, not normally found in blood"),
    ("R79", "Other abnormal findings of blood chemistry"),
    ("R80", "Isolated proteinuria"), ("R81", "Glycosuria"),
    ("R82", "Other abnormal findings in urine"),
    ("R85", "Abnormal findings in specimens from digestive organs and abdominal cavity"),
    ("R87", "Abnormal findings in specimens from female genital organs"),
    ("R94", "Abnormal results of function studies"),
    ("R95", "Sudden infant death syndrome"),
    ("R96", "Other sudden death, cause unknown"),
    ("R98", "Unattended death"),
    ("R99", "Other ill-defined and unspecified causes of mortality"),
])

# Chapter XIX Injury (S00–T98) — pick most common
_icd_block("XIX Injury", "Head / neck / trunk / limb / poisoning / burns", [
    ("S00", "Superficial injury of head"),
    ("S01", "Open wound of head"),
    ("S02", "Fracture of skull and facial bones"),
    ("S06", "Intracranial injury"),
    ("S09", "Other and unspecified injuries of head"),
    ("S10", "Superficial injury of neck"),
    ("S20", "Superficial injury of thorax"),
    ("S22", "Fracture of rib(s), sternum and thoracic spine"),
    ("S30", "Superficial injury of abdomen, lower back and pelvis"),
    ("S32", "Fracture of lumbar spine and pelvis"),
    ("S42", "Fracture of shoulder and upper arm"),
    ("S52", "Fracture of forearm"),
    ("S62", "Fracture at wrist and hand level"),
    ("S72", "Fracture of femur"),
    ("S82", "Fracture of lower leg, including ankle"),
    ("S92", "Fracture of foot, except ankle"),
    ("T14", "Injury of unspecified body region"),
    ("T20", "Burn and corrosion of head and neck"),
    ("T24", "Burn and corrosion of lower limb, except ankle and foot"),
    ("T30", "Burn and corrosion, body region unspecified"),
    ("T36", "Poisoning by systemic antibiotics"),
    ("T39", "Poisoning by non-opioid analgesics, antipyretics and antirheumatics"),
    ("T40", "Poisoning by narcotics and psychodysleptics [hallucinogens]"),
    ("T42", "Poisoning by antiepileptic, sedative-hypnotic, anti-parkinsonism and other CNS-depressant drugs"),
    ("T44", "Poisoning by drugs primarily affecting the autonomic nervous system"),
    ("T50", "Poisoning by diuretics and other and unspecified drugs, medicaments and biological substances"),
    ("T78", "Adverse effects, not elsewhere classified"),
    ("T80", "Complications following infusion, transfusion and therapeutic injection"),
    ("T81", "Complications of procedures, not elsewhere classified"),
    ("T88", "Other complications of surgical and medical care, NEC"),
])

# Chapter XX External causes (V01–Y98) — top-level only
_icd_block("XX External", "External causes of morbidity and mortality", [
    ("V01", "Pedestrian injured in collision with pedal cycle"),
    ("V40", "Car occupant injured in collision with pedestrian or animal"),
    ("V89", "Motor- or nonmotor-vehicle accident, type of vehicle unspecified"),
    ("W00", "Fall on same level involving ice and snow"),
    ("W19", "Unspecified fall"),
    ("X44", "Accidental poisoning by other and unspecified drugs, medicaments and biological substances"),
    ("X60", "Intentional self-poisoning by and exposure to nonopioid analgesics"),
    ("X95", "Assault by other and unspecified firearm discharge"),
    ("Y10", "Poisoning by and exposure to nonopioid analgesics, undetermined intent"),
    ("Y65", "Other misadventures during surgical and medical care"),
    ("Y83", "Surgical operation and other surgical procedures as the cause of abnormal reaction of the patient"),
    ("Y95", "Nosocomial condition"),
])

# Chapter XXI Z-codes (factors influencing health status)
_icd_block("XXI Health status", "Factors influencing health status", [
    ("Z00", "General examination and investigation of persons without complaint or reported diagnosis"),
    ("Z01", "Other special examinations and investigations of persons without complaint"),
    ("Z03", "Medical observation and evaluation for suspected diseases and conditions"),
    ("Z11", "Special screening examination for infectious and parasitic diseases"),
    ("Z12", "Special screening examination for neoplasms"),
    ("Z20", "Contact with and (suspected) exposure to communicable diseases"),
    ("Z21", "Asymptomatic HIV infection status"),
    ("Z23", "Need for immunization against single bacterial diseases"),
    ("Z30", "Contraceptive management"),
    ("Z34", "Supervision of normal pregnancy"),
    ("Z37", "Outcome of delivery"),
    ("Z38", "Liveborn infants according to place of birth"),
    ("Z51", "Other medical care"),
    ("Z63", "Other problems related to primary support group, including family circumstances"),
    ("Z72", "Problems related to lifestyle"),
    ("Z76", "Persons encountering health services in other circumstances"),
    ("Z85", "Personal history of malignant neoplasm"),
    ("Z87", "Personal history of other diseases and conditions"),
    ("Z90", "Acquired absence of organs NEC"),
    ("Z95", "Presence of cardiac and vascular implants and grafts"),
    ("Z96", "Presence of other functional implants"),
    ("Z99", "Dependence on enabling machines and devices NEC"),
])

# ---------------------------------------------------------------- ATC core
# WHO Anatomical Therapeutic Chemical Classification (CC0). We bundle the
# 14 anatomical mains + selected 3rd-5th level codes (≥300 rows).

ATC: list[tuple[str, str, str]] = []


def _atc(code: str, term: str, hier: str) -> None:
    ATC.append((code, term, hier))


# Level 1 (14)
_atc("A", "Alimentary tract and metabolism", "")
_atc("B", "Blood and blood forming organs", "")
_atc("C", "Cardiovascular system", "")
_atc("D", "Dermatologicals", "")
_atc("G", "Genito urinary system and sex hormones", "")
_atc("H", "Systemic hormonal preparations, excl. sex hormones and insulins", "")
_atc("J", "Antiinfectives for systemic use", "")
_atc("L", "Antineoplastic and immunomodulating agents", "")
_atc("M", "Musculo-skeletal system", "")
_atc("N", "Nervous system", "")
_atc("P", "Antiparasitic products, insecticides and repellents", "")
_atc("R", "Respiratory system", "")
_atc("S", "Sensory organs", "")
_atc("V", "Various", "")

# A — Alimentary
A_LEVEL2 = [
    ("A01", "Stomatological preparations"),
    ("A02", "Drugs for acid related disorders"),
    ("A03", "Drugs for functional gastrointestinal disorders"),
    ("A04", "Antiemetics and antinauseants"),
    ("A05", "Bile and liver therapy"),
    ("A06", "Drugs for constipation"),
    ("A07", "Antidiarrheals, intestinal antiinflammatory/antiinfective agents"),
    ("A08", "Antiobesity preparations, excl. diet products"),
    ("A09", "Digestives, incl. enzymes"),
    ("A10", "Drugs used in diabetes"),
    ("A11", "Vitamins"),
    ("A12", "Mineral supplements"),
    ("A14", "Anabolic agents for systemic use"),
    ("A16", "Other alimentary tract and metabolism products"),
]
for c, t in A_LEVEL2:
    _atc(c, t, "A")
A_SUB = [
    ("A02BC01", "Omeprazole", "A|A02|A02B|A02BC"),
    ("A02BC02", "Pantoprazole", "A|A02|A02B|A02BC"),
    ("A02BC03", "Lansoprazole", "A|A02|A02B|A02BC"),
    ("A02BC05", "Esomeprazole", "A|A02|A02B|A02BC"),
    ("A02BA02", "Ranitidine", "A|A02|A02B|A02BA"),
    ("A02BA03", "Famotidine", "A|A02|A02B|A02BA"),
    ("A03FA01", "Metoclopramide", "A|A03|A03F|A03FA"),
    ("A04AA01", "Ondansetron", "A|A04|A04A|A04AA"),
    ("A04AA02", "Granisetron", "A|A04|A04A|A04AA"),
    ("A04AA05", "Palonosetron", "A|A04|A04A|A04AA"),
    ("A06AB02", "Bisacodyl", "A|A06|A06A|A06AB"),
    ("A06AD11", "Lactulose", "A|A06|A06A|A06AD"),
    ("A07EC01", "Sulfasalazine", "A|A07|A07E|A07EC"),
    ("A07EC02", "Mesalazine", "A|A07|A07E|A07EC"),
    ("A10BA02", "Metformin", "A|A10|A10B|A10BA"),
    ("A10BB01", "Glibenclamide", "A|A10|A10B|A10BB"),
    ("A10BB07", "Glipizide", "A|A10|A10B|A10BB"),
    ("A10BB09", "Gliclazide", "A|A10|A10B|A10BB"),
    ("A10BB12", "Glimepiride", "A|A10|A10B|A10BB"),
    ("A10BD07", "Metformin and sitagliptin", "A|A10|A10B|A10BD"),
    ("A10BG01", "Troglitazone", "A|A10|A10B|A10BG"),
    ("A10BG02", "Rosiglitazone", "A|A10|A10B|A10BG"),
    ("A10BG03", "Pioglitazone", "A|A10|A10B|A10BG"),
    ("A10BH01", "Sitagliptin", "A|A10|A10B|A10BH"),
    ("A10BH02", "Vildagliptin", "A|A10|A10B|A10BH"),
    ("A10BJ01", "Exenatide", "A|A10|A10B|A10BJ"),
    ("A10BJ02", "Liraglutide", "A|A10|A10B|A10BJ"),
    ("A10BJ05", "Dulaglutide", "A|A10|A10B|A10BJ"),
    ("A10BJ06", "Semaglutide", "A|A10|A10B|A10BJ"),
    ("A10BK01", "Dapagliflozin", "A|A10|A10B|A10BK"),
    ("A10BK02", "Canagliflozin", "A|A10|A10B|A10BK"),
    ("A10BK03", "Empagliflozin", "A|A10|A10B|A10BK"),
    ("A10AB01", "Insulin (human) – short acting", "A|A10|A10A|A10AB"),
    ("A10AC01", "Insulin (human) – intermediate acting", "A|A10|A10A|A10AC"),
    ("A10AE04", "Insulin glargine", "A|A10|A10A|A10AE"),
    ("A10AE05", "Insulin detemir", "A|A10|A10A|A10AE"),
    ("A11CC05", "Colecalciferol", "A|A11|A11C|A11CC"),
    ("A12AA04", "Calcium carbonate", "A|A12|A12A|A12AA"),
]
for c, t, h in A_SUB:
    _atc(c, t, h)

# B — Blood
B_LEVEL2 = [
    ("B01", "Antithrombotic agents"),
    ("B02", "Antihemorrhagics"),
    ("B03", "Antianemic preparations"),
    ("B05", "Blood substitutes and perfusion solutions"),
    ("B06", "Other haematological agents"),
]
for c, t in B_LEVEL2:
    _atc(c, t, "B")
B_SUB = [
    ("B01AA03", "Warfarin", "B|B01|B01A|B01AA"),
    ("B01AB01", "Heparin", "B|B01|B01A|B01AB"),
    ("B01AB04", "Dalteparin", "B|B01|B01A|B01AB"),
    ("B01AB05", "Enoxaparin", "B|B01|B01A|B01AB"),
    ("B01AC04", "Clopidogrel", "B|B01|B01A|B01AC"),
    ("B01AC06", "Acetylsalicylic acid", "B|B01|B01A|B01AC"),
    ("B01AC22", "Prasugrel", "B|B01|B01A|B01AC"),
    ("B01AC24", "Ticagrelor", "B|B01|B01A|B01AC"),
    ("B01AE07", "Dabigatran etexilate", "B|B01|B01A|B01AE"),
    ("B01AF01", "Rivaroxaban", "B|B01|B01A|B01AF"),
    ("B01AF02", "Apixaban", "B|B01|B01A|B01AF"),
    ("B01AF03", "Edoxaban", "B|B01|B01A|B01AF"),
    ("B02BX04", "Romiplostim", "B|B02|B02B|B02BX"),
    ("B03AA02", "Ferrous fumarate", "B|B03|B03A|B03AA"),
    ("B03AA07", "Ferrous sulfate", "B|B03|B03A|B03AA"),
    ("B03BA01", "Cyanocobalamin", "B|B03|B03B|B03BA"),
    ("B03BB01", "Folic acid", "B|B03|B03B|B03BB"),
    ("B03XA01", "Erythropoietin", "B|B03|B03X|B03XA"),
    ("B03XA02", "Darbepoetin alfa", "B|B03|B03X|B03XA"),
]
for c, t, h in B_SUB:
    _atc(c, t, h)

# C — Cardiovascular
C_LEVEL2 = [
    ("C01", "Cardiac therapy"),
    ("C02", "Antihypertensives"),
    ("C03", "Diuretics"),
    ("C04", "Peripheral vasodilators"),
    ("C05", "Vasoprotectives"),
    ("C07", "Beta blocking agents"),
    ("C08", "Calcium channel blockers"),
    ("C09", "Agents acting on the renin-angiotensin system"),
    ("C10", "Lipid modifying agents"),
]
for c, t in C_LEVEL2:
    _atc(c, t, "C")
C_SUB = [
    ("C01AA05", "Digoxin", "C|C01|C01A|C01AA"),
    ("C01BD01", "Amiodarone", "C|C01|C01B|C01BD"),
    ("C01CA04", "Dopamine", "C|C01|C01C|C01CA"),
    ("C01CA07", "Dobutamine", "C|C01|C01C|C01CA"),
    ("C01CA24", "Epinephrine", "C|C01|C01C|C01CA"),
    ("C01EB17", "Ivabradine", "C|C01|C01E|C01EB"),
    ("C03AA03", "Hydrochlorothiazide", "C|C03|C03A|C03AA"),
    ("C03BA04", "Chlortalidone", "C|C03|C03B|C03BA"),
    ("C03CA01", "Furosemide", "C|C03|C03C|C03CA"),
    ("C03CA02", "Bumetanide", "C|C03|C03C|C03CA"),
    ("C03DA01", "Spironolactone", "C|C03|C03D|C03DA"),
    ("C03DA04", "Eplerenone", "C|C03|C03D|C03DA"),
    ("C07AA05", "Propranolol", "C|C07|C07A|C07AA"),
    ("C07AB02", "Metoprolol", "C|C07|C07A|C07AB"),
    ("C07AB03", "Atenolol", "C|C07|C07A|C07AB"),
    ("C07AB07", "Bisoprolol", "C|C07|C07A|C07AB"),
    ("C07AB12", "Nebivolol", "C|C07|C07A|C07AB"),
    ("C07AG01", "Labetalol", "C|C07|C07A|C07AG"),
    ("C07AG02", "Carvedilol", "C|C07|C07A|C07AG"),
    ("C08CA01", "Amlodipine", "C|C08|C08C|C08CA"),
    ("C08CA05", "Nifedipine", "C|C08|C08C|C08CA"),
    ("C08CA13", "Lercanidipine", "C|C08|C08C|C08CA"),
    ("C08DA01", "Verapamil", "C|C08|C08D|C08DA"),
    ("C08DB01", "Diltiazem", "C|C08|C08D|C08DB"),
    ("C09AA01", "Captopril", "C|C09|C09A|C09AA"),
    ("C09AA02", "Enalapril", "C|C09|C09A|C09AA"),
    ("C09AA03", "Lisinopril", "C|C09|C09A|C09AA"),
    ("C09AA05", "Ramipril", "C|C09|C09A|C09AA"),
    ("C09AA08", "Cilazapril", "C|C09|C09A|C09AA"),
    ("C09AA10", "Trandolapril", "C|C09|C09A|C09AA"),
    ("C09CA01", "Losartan", "C|C09|C09C|C09CA"),
    ("C09CA03", "Valsartan", "C|C09|C09C|C09CA"),
    ("C09CA06", "Candesartan", "C|C09|C09C|C09CA"),
    ("C09CA07", "Telmisartan", "C|C09|C09C|C09CA"),
    ("C09CA08", "Olmesartan medoxomil", "C|C09|C09C|C09CA"),
    ("C09DX04", "Sacubitril and valsartan", "C|C09|C09D|C09DX"),
    ("C10AA01", "Simvastatin", "C|C10|C10A|C10AA"),
    ("C10AA02", "Lovastatin", "C|C10|C10A|C10AA"),
    ("C10AA03", "Pravastatin", "C|C10|C10A|C10AA"),
    ("C10AA04", "Fluvastatin", "C|C10|C10A|C10AA"),
    ("C10AA05", "Atorvastatin", "C|C10|C10A|C10AA"),
    ("C10AA07", "Rosuvastatin", "C|C10|C10A|C10AA"),
    ("C10AA08", "Pitavastatin", "C|C10|C10A|C10AA"),
    ("C10AB04", "Gemfibrozil", "C|C10|C10A|C10AB"),
    ("C10AB05", "Fenofibrate", "C|C10|C10A|C10AB"),
    ("C10AX09", "Ezetimibe", "C|C10|C10A|C10AX"),
    ("C10AX13", "Evolocumab", "C|C10|C10A|C10AX"),
]
for c, t, h in C_SUB:
    _atc(c, t, h)

# J — Antiinfectives
J_LEVEL2 = [
    ("J01", "Antibacterials for systemic use"),
    ("J02", "Antimycotics for systemic use"),
    ("J04", "Antimycobacterials"),
    ("J05", "Antivirals for systemic use"),
    ("J06", "Immune sera and immunoglobulins"),
    ("J07", "Vaccines"),
]
for c, t in J_LEVEL2:
    _atc(c, t, "J")
J_SUB = [
    ("J01AA02", "Doxycycline", "J|J01|J01A|J01AA"),
    ("J01AA07", "Tetracycline", "J|J01|J01A|J01AA"),
    ("J01CA04", "Amoxicillin", "J|J01|J01C|J01CA"),
    ("J01CA08", "Pivmecillinam", "J|J01|J01C|J01CA"),
    ("J01CE02", "Phenoxymethylpenicillin", "J|J01|J01C|J01CE"),
    ("J01CR02", "Amoxicillin and beta-lactamase inhibitor", "J|J01|J01C|J01CR"),
    ("J01CR05", "Piperacillin and beta-lactamase inhibitor", "J|J01|J01C|J01CR"),
    ("J01DB01", "Cefalexin", "J|J01|J01D|J01DB"),
    ("J01DC02", "Cefuroxime", "J|J01|J01D|J01DC"),
    ("J01DD04", "Ceftriaxone", "J|J01|J01D|J01DD"),
    ("J01DD08", "Cefixime", "J|J01|J01D|J01DD"),
    ("J01DH02", "Meropenem", "J|J01|J01D|J01DH"),
    ("J01DH51", "Imipenem and cilastatin", "J|J01|J01D|J01DH"),
    ("J01EE01", "Sulfamethoxazole and trimethoprim", "J|J01|J01E|J01EE"),
    ("J01FA01", "Erythromycin", "J|J01|J01F|J01FA"),
    ("J01FA09", "Clarithromycin", "J|J01|J01F|J01FA"),
    ("J01FA10", "Azithromycin", "J|J01|J01F|J01FA"),
    ("J01FF01", "Clindamycin", "J|J01|J01F|J01FF"),
    ("J01GB03", "Gentamicin", "J|J01|J01G|J01GB"),
    ("J01GB06", "Amikacin", "J|J01|J01G|J01GB"),
    ("J01MA01", "Ofloxacin", "J|J01|J01M|J01MA"),
    ("J01MA02", "Ciprofloxacin", "J|J01|J01M|J01MA"),
    ("J01MA12", "Levofloxacin", "J|J01|J01M|J01MA"),
    ("J01MA14", "Moxifloxacin", "J|J01|J01M|J01MA"),
    ("J01XA01", "Vancomycin", "J|J01|J01X|J01XA"),
    ("J01XD01", "Metronidazole", "J|J01|J01X|J01XD"),
    ("J02AC01", "Fluconazole", "J|J02|J02A|J02AC"),
    ("J02AC03", "Voriconazole", "J|J02|J02A|J02AC"),
    ("J02AC04", "Posaconazole", "J|J02|J02A|J02AC"),
    ("J04AB02", "Rifampicin", "J|J04|J04A|J04AB"),
    ("J04AC01", "Isoniazid", "J|J04|J04A|J04AC"),
    ("J05AB01", "Aciclovir", "J|J05|J05A|J05AB"),
    ("J05AB14", "Valganciclovir", "J|J05|J05A|J05AB"),
    ("J05AF05", "Lamivudine", "J|J05|J05A|J05AF"),
    ("J05AF07", "Tenofovir disoproxil", "J|J05|J05A|J05AF"),
    ("J05AH02", "Oseltamivir", "J|J05|J05A|J05AH"),
    ("J05AP01", "Ribavirin", "J|J05|J05A|J05AP"),
    ("J05AP07", "Sofosbuvir", "J|J05|J05A|J05AP"),
    ("J05AR03", "Tenofovir disoproxil and emtricitabine", "J|J05|J05A|J05AR"),
]
for c, t, h in J_SUB:
    _atc(c, t, h)

# L — Antineoplastic
L_LEVEL2 = [
    ("L01", "Antineoplastic agents"),
    ("L02", "Endocrine therapy"),
    ("L03", "Immunostimulants"),
    ("L04", "Immunosuppressants"),
]
for c, t in L_LEVEL2:
    _atc(c, t, "L")
L_SUB = [
    ("L01AA01", "Cyclophosphamide", "L|L01|L01A|L01AA"),
    ("L01AA02", "Chlorambucil", "L|L01|L01A|L01AA"),
    ("L01BA01", "Methotrexate", "L|L01|L01B|L01BA"),
    ("L01BC02", "Fluorouracil", "L|L01|L01B|L01BC"),
    ("L01BC06", "Capecitabine", "L|L01|L01B|L01BC"),
    ("L01CB01", "Etoposide", "L|L01|L01C|L01CB"),
    ("L01CD01", "Paclitaxel", "L|L01|L01C|L01CD"),
    ("L01CD02", "Docetaxel", "L|L01|L01C|L01CD"),
    ("L01XA01", "Cisplatin", "L|L01|L01X|L01XA"),
    ("L01XA02", "Carboplatin", "L|L01|L01X|L01XA"),
    ("L01XA03", "Oxaliplatin", "L|L01|L01X|L01XA"),
    ("L01XC02", "Rituximab", "L|L01|L01X|L01XC"),
    ("L01XC03", "Trastuzumab", "L|L01|L01X|L01XC"),
    ("L01XC07", "Bevacizumab", "L|L01|L01X|L01XC"),
    ("L01XC08", "Panitumumab", "L|L01|L01X|L01XC"),
    ("L01XC17", "Nivolumab", "L|L01|L01X|L01XC"),
    ("L01XC18", "Pembrolizumab", "L|L01|L01X|L01XC"),
    ("L01XE01", "Imatinib", "L|L01|L01X|L01XE"),
    ("L01XE03", "Erlotinib", "L|L01|L01X|L01XE"),
    ("L01XE07", "Lapatinib", "L|L01|L01X|L01XE"),
    ("L01XE13", "Afatinib", "L|L01|L01X|L01XE"),
    ("L02BA01", "Tamoxifen", "L|L02|L02B|L02BA"),
    ("L02BB03", "Bicalutamide", "L|L02|L02B|L02BB"),
    ("L02BG03", "Anastrozole", "L|L02|L02B|L02BG"),
    ("L02BG04", "Letrozole", "L|L02|L02B|L02BG"),
    ("L02BG06", "Exemestane", "L|L02|L02B|L02BG"),
    ("L03AB07", "Interferon beta-1a", "L|L03|L03A|L03AB"),
    ("L04AA13", "Leflunomide", "L|L04|L04A|L04AA"),
    ("L04AA27", "Fingolimod", "L|L04|L04A|L04AA"),
    ("L04AD01", "Ciclosporin", "L|L04|L04A|L04AD"),
    ("L04AD02", "Tacrolimus", "L|L04|L04A|L04AD"),
    ("L04AX01", "Azathioprine", "L|L04|L04A|L04AX"),
    ("L04AX03", "Methotrexate (immunosuppressant)", "L|L04|L04A|L04AX"),
]
for c, t, h in L_SUB:
    _atc(c, t, h)

# N — Nervous system (large)
N_LEVEL2 = [
    ("N01", "Anesthetics"),
    ("N02", "Analgesics"),
    ("N03", "Antiepileptics"),
    ("N04", "Anti-Parkinson drugs"),
    ("N05", "Psycholeptics"),
    ("N06", "Psychoanaleptics"),
    ("N07", "Other nervous system drugs"),
]
for c, t in N_LEVEL2:
    _atc(c, t, "N")
N_SUB = [
    ("N02AA01", "Morphine", "N|N02|N02A|N02AA"),
    ("N02AA05", "Oxycodone", "N|N02|N02A|N02AA"),
    ("N02AB02", "Pethidine", "N|N02|N02A|N02AB"),
    ("N02AB03", "Fentanyl", "N|N02|N02A|N02AB"),
    ("N02AX02", "Tramadol", "N|N02|N02A|N02AX"),
    ("N02BA01", "Acetylsalicylic acid (analgesic)", "N|N02|N02B|N02BA"),
    ("N02BE01", "Paracetamol", "N|N02|N02B|N02BE"),
    ("N03AB02", "Phenytoin", "N|N03|N03A|N03AB"),
    ("N03AF01", "Carbamazepine", "N|N03|N03A|N03AF"),
    ("N03AG01", "Valproic acid", "N|N03|N03A|N03AG"),
    ("N03AX09", "Lamotrigine", "N|N03|N03A|N03AX"),
    ("N03AX12", "Gabapentin", "N|N03|N03A|N03AX"),
    ("N03AX14", "Levetiracetam", "N|N03|N03A|N03AX"),
    ("N03AX16", "Pregabalin", "N|N03|N03A|N03AX"),
    ("N04BA02", "Levodopa and decarboxylase inhibitor", "N|N04|N04B|N04BA"),
    ("N04BC05", "Pramipexole", "N|N04|N04B|N04BC"),
    ("N05AA01", "Chlorpromazine", "N|N05|N05A|N05AA"),
    ("N05AD01", "Haloperidol", "N|N05|N05A|N05AD"),
    ("N05AH03", "Olanzapine", "N|N05|N05A|N05AH"),
    ("N05AH04", "Quetiapine", "N|N05|N05A|N05AH"),
    ("N05AX08", "Risperidone", "N|N05|N05A|N05AX"),
    ("N05AX12", "Aripiprazole", "N|N05|N05A|N05AX"),
    ("N05BA01", "Diazepam", "N|N05|N05B|N05BA"),
    ("N05BA04", "Oxazepam", "N|N05|N05B|N05BA"),
    ("N05BA06", "Lorazepam", "N|N05|N05B|N05BA"),
    ("N05BA12", "Alprazolam", "N|N05|N05B|N05BA"),
    ("N05CD08", "Midazolam", "N|N05|N05C|N05CD"),
    ("N05CF01", "Zopiclone", "N|N05|N05C|N05CF"),
    ("N05CF02", "Zolpidem", "N|N05|N05C|N05CF"),
    ("N06AA09", "Amitriptyline", "N|N06|N06A|N06AA"),
    ("N06AB03", "Fluoxetine", "N|N06|N06A|N06AB"),
    ("N06AB04", "Citalopram", "N|N06|N06A|N06AB"),
    ("N06AB05", "Paroxetine", "N|N06|N06A|N06AB"),
    ("N06AB06", "Sertraline", "N|N06|N06A|N06AB"),
    ("N06AB10", "Escitalopram", "N|N06|N06A|N06AB"),
    ("N06AX11", "Mirtazapine", "N|N06|N06A|N06AX"),
    ("N06AX16", "Venlafaxine", "N|N06|N06A|N06AX"),
    ("N06AX21", "Duloxetine", "N|N06|N06A|N06AX"),
    ("N06DA02", "Donepezil", "N|N06|N06D|N06DA"),
    ("N06DA03", "Rivastigmine", "N|N06|N06D|N06DA"),
    ("N06DX01", "Memantine", "N|N06|N06D|N06DX"),
]
for c, t, h in N_SUB:
    _atc(c, t, h)

# R — Respiratory
R_LEVEL2 = [
    ("R01", "Nasal preparations"),
    ("R03", "Drugs for obstructive airway diseases"),
    ("R05", "Cough and cold preparations"),
    ("R06", "Antihistamines for systemic use"),
]
for c, t in R_LEVEL2:
    _atc(c, t, "R")
R_SUB = [
    ("R03AC02", "Salbutamol", "R|R03|R03A|R03AC"),
    ("R03AC03", "Terbutaline", "R|R03|R03A|R03AC"),
    ("R03AC12", "Salmeterol", "R|R03|R03A|R03AC"),
    ("R03AC13", "Formoterol", "R|R03|R03A|R03AC"),
    ("R03AC18", "Indacaterol", "R|R03|R03A|R03AC"),
    ("R03BA01", "Beclometasone", "R|R03|R03B|R03BA"),
    ("R03BA02", "Budesonide", "R|R03|R03B|R03BA"),
    ("R03BA05", "Fluticasone", "R|R03|R03B|R03BA"),
    ("R03BB01", "Ipratropium bromide", "R|R03|R03B|R03BB"),
    ("R03BB04", "Tiotropium bromide", "R|R03|R03B|R03BB"),
    ("R03DA04", "Theophylline", "R|R03|R03D|R03DA"),
    ("R03DC03", "Montelukast", "R|R03|R03D|R03DC"),
    ("R06AE07", "Cetirizine", "R|R06|R06A|R06AE"),
    ("R06AE09", "Levocetirizine", "R|R06|R06A|R06AE"),
    ("R06AX13", "Loratadine", "R|R06|R06A|R06AX"),
    ("R06AX27", "Desloratadine", "R|R06|R06A|R06AX"),
    ("R06AX26", "Fexofenadine", "R|R06|R06A|R06AX"),
]
for c, t, h in R_SUB:
    _atc(c, t, h)

# H — Hormonal
H_SUB = [
    ("H02AB02", "Dexamethasone", "H|H02|H02A|H02AB"),
    ("H02AB06", "Prednisolone", "H|H02|H02A|H02AB"),
    ("H02AB07", "Prednisone", "H|H02|H02A|H02AB"),
    ("H02AB09", "Hydrocortisone", "H|H02|H02A|H02AB"),
    ("H02AB10", "Cortisone", "H|H02|H02A|H02AB"),
    ("H03AA01", "Levothyroxine sodium", "H|H03|H03A|H03AA"),
    ("H03BA02", "Propylthiouracil", "H|H03|H03B|H03BA"),
    ("H03BB02", "Carbimazole", "H|H03|H03B|H03BB"),
    ("H04AA01", "Glucagon", "H|H04|H04A|H04AA"),
    ("H05BA01", "Calcitonin (salmon synthetic)", "H|H05|H05B|H05BA"),
]
for c, t, h in H_SUB:
    _atc(c, t, h)

# M — Musculoskeletal
M_SUB = [
    ("M01AB05", "Diclofenac", "M|M01|M01A|M01AB"),
    ("M01AE01", "Ibuprofen", "M|M01|M01A|M01AE"),
    ("M01AE02", "Naproxen", "M|M01|M01A|M01AE"),
    ("M01AH01", "Celecoxib", "M|M01|M01A|M01AH"),
    ("M01AH05", "Etoricoxib", "M|M01|M01A|M01AH"),
    ("M01CB01", "Sodium aurothiomalate", "M|M01|M01C|M01CB"),
    ("M04AA01", "Allopurinol", "M|M04|M04A|M04AA"),
    ("M04AA03", "Febuxostat", "M|M04|M04A|M04AA"),
    ("M05BA04", "Alendronic acid", "M|M05|M05B|M05BA"),
    ("M05BA08", "Zoledronic acid", "M|M05|M05B|M05BA"),
]
for c, t, h in M_SUB:
    _atc(c, t, h)

# D — Dermatologicals (selected)
D_SUB = [
    ("D01AC01", "Clotrimazole", "D|D01|D01A|D01AC"),
    ("D06AX09", "Mupirocin", "D|D06|D06A|D06AX"),
    ("D07AB02", "Hydrocortisone butyrate", "D|D07|D07A|D07AB"),
    ("D07AC01", "Betamethasone (topical)", "D|D07|D07A|D07AC"),
    ("D08AC02", "Chlorhexidine", "D|D08|D08A|D08AC"),
    ("D10AD01", "Tretinoin", "D|D10|D10A|D10AD"),
]
for c, t, h in D_SUB:
    _atc(c, t, h)


# ---------------------------------------------------------------- LOINC core
# Regenstrief LOINC (public domain). Curated common laboratory tests.

LOINC: list[tuple[str, str, str]] = []


def _loinc(code: str, term: str, hier: str) -> None:
    LOINC.append((code, term, hier))


LOINC_CORE = [
    # Hematology / CBC
    ("718-7", "Hemoglobin [Mass/volume] in Blood", "Hematology|CBC"),
    ("4544-3", "Hematocrit [Volume Fraction] of Blood by Automated count", "Hematology|CBC"),
    ("789-8", "Erythrocytes [#/volume] in Blood by Automated count", "Hematology|CBC"),
    ("787-2", "MCV [Entitic volume] by Automated count", "Hematology|CBC"),
    ("785-6", "MCH [Entitic mass] by Automated count", "Hematology|CBC"),
    ("786-4", "MCHC [Mass/volume] by Automated count", "Hematology|CBC"),
    ("21000-5", "Erythrocyte distribution width [Entitic volume] by Automated count", "Hematology|CBC"),
    ("777-3", "Platelets [#/volume] in Blood by Automated count", "Hematology|CBC"),
    ("6690-2", "Leukocytes [#/volume] in Blood by Automated count", "Hematology|CBC"),
    ("770-8", "Neutrophils/100 leukocytes in Blood by Automated count", "Hematology|CBC"),
    ("736-9", "Lymphocytes/100 leukocytes in Blood by Automated count", "Hematology|CBC"),
    ("5905-5", "Monocytes/100 leukocytes in Blood by Automated count", "Hematology|CBC"),
    ("713-8", "Eosinophils/100 leukocytes in Blood by Automated count", "Hematology|CBC"),
    ("706-2", "Basophils/100 leukocytes in Blood by Automated count", "Hematology|CBC"),
    ("38518-7", "Neutrophils [#/volume] in Blood by Automated count", "Hematology|CBC"),
    # Coagulation
    ("5902-2", "Prothrombin time (PT)", "Hematology|Coagulation"),
    ("6301-6", "INR in Platelet poor plasma by Coagulation assay", "Hematology|Coagulation"),
    ("14979-9", "aPTT in Platelet poor plasma by Coagulation assay", "Hematology|Coagulation"),
    ("3255-7", "Fibrinogen [Mass/volume] in Platelet poor plasma by Coagulation assay", "Hematology|Coagulation"),
    ("48065-7", "D-dimer FEU [Mass/volume] in Platelet poor plasma", "Hematology|Coagulation"),
    # Chemistry – metabolic
    ("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "Chemistry|Metabolic"),
    ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "Chemistry|Metabolic"),
    ("2160-0", "Creatinine [Mass/volume] in Serum or Plasma", "Chemistry|Renal"),
    ("3094-0", "Urea nitrogen [Mass/volume] in Serum or Plasma", "Chemistry|Renal"),
    ("33914-3", "Glomerular filtration rate/1.73 sq M.predicted by Creatinine-based formula (MDRD)", "Chemistry|Renal"),
    ("2823-3", "Potassium [Moles/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("2075-0", "Chloride [Moles/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("1963-8", "Bicarbonate [Moles/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("17861-6", "Calcium [Mass/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("2777-1", "Phosphate [Mass/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("19123-9", "Magnesium [Moles/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("2885-2", "Protein [Mass/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("1751-7", "Albumin [Mass/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("10834-0", "Globulin [Mass/volume] in Serum by Calculation", "Chemistry|Liver"),
    ("1968-7", "Bilirubin.direct [Mass/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("1975-2", "Bilirubin.total [Mass/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("1742-6", "Alanine aminotransferase (ALT) [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("1920-8", "Aspartate aminotransferase (AST) [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("6768-6", "Alkaline phosphatase [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("2324-2", "Gamma glutamyl transferase [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("2532-0", "Lactate dehydrogenase [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("2157-6", "Creatine kinase [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Cardiac"),
    ("13969-1", "Creatine kinase.MB [Mass/volume] in Serum or Plasma", "Chemistry|Cardiac"),
    ("10839-9", "Troponin I.cardiac [Mass/volume] in Serum or Plasma", "Chemistry|Cardiac"),
    ("33762-6", "NT-proBNP [Mass/volume] in Serum or Plasma", "Chemistry|Cardiac"),
    # Lipids
    ("2093-3", "Cholesterol [Mass/volume] in Serum or Plasma", "Chemistry|Lipids"),
    ("2571-8", "Triglyceride [Mass/volume] in Serum or Plasma", "Chemistry|Lipids"),
    ("2085-9", "Cholesterol in HDL [Mass/volume] in Serum or Plasma", "Chemistry|Lipids"),
    ("13457-7", "Cholesterol in LDL [Mass/volume] in Serum or Plasma by calculation", "Chemistry|Lipids"),
    ("3043-7", "Lactate [Mass/volume] in Serum or Plasma", "Chemistry|Other"),
    # Endocrine
    ("3016-3", "Thyrotropin [Units/volume] in Serum or Plasma", "Endocrine|Thyroid"),
    ("3024-7", "Thyroxine (T4) free [Mass/volume] in Serum or Plasma", "Endocrine|Thyroid"),
    ("3051-0", "Triiodothyronine (T3) free [Mass/volume] in Serum or Plasma", "Endocrine|Thyroid"),
    ("2986-8", "Testosterone [Mass/volume] in Serum or Plasma", "Endocrine|Sex hormones"),
    ("83088-6", "Estradiol [Mass/volume] in Serum or Plasma", "Endocrine|Sex hormones"),
    ("2243-4", "Estriol [Mass/volume] in Serum or Plasma", "Endocrine|Sex hormones"),
    ("19080-1", "Estradiol panel - Serum or Plasma", "Endocrine|Sex hormones"),
    ("2839-9", "Progesterone [Mass/volume] in Serum or Plasma", "Endocrine|Sex hormones"),
    ("2842-3", "Prolactin [Mass/volume] in Serum or Plasma", "Endocrine|Sex hormones"),
    # Inflammatory
    ("1988-5", "C reactive protein [Mass/volume] in Serum or Plasma", "Chemistry|Inflammation"),
    ("4537-7", "Erythrocyte sedimentation rate (ESR) by Westergren", "Hematology|Inflammation"),
    ("48421-2", "Procalcitonin [Mass/volume] in Serum or Plasma", "Chemistry|Inflammation"),
    # Urinalysis
    ("5811-5", "Specific gravity of Urine by Test strip", "Urinalysis"),
    ("5803-2", "pH of Urine by Test strip", "Urinalysis"),
    ("5804-0", "Protein [Mass/volume] in Urine by Test strip", "Urinalysis"),
    ("5792-7", "Glucose [Mass/volume] in Urine by Test strip", "Urinalysis"),
    ("5797-6", "Ketones [Mass/volume] in Urine by Test strip", "Urinalysis"),
    ("5794-3", "Hemoglobin [Mass/volume] in Urine by Test strip", "Urinalysis"),
    ("5802-4", "Nitrite [Mass/volume] in Urine by Test strip", "Urinalysis"),
    ("5799-2", "Leukocyte esterase [Mass/volume] in Urine by Test strip", "Urinalysis"),
    ("2161-8", "Creatinine [Mass/volume] in Urine", "Urinalysis"),
    ("13986-5", "Albumin/Creatinine [Mass Ratio] in Urine", "Urinalysis"),
    ("2890-2", "Albumin [Mass/volume] in 24 hour Urine", "Urinalysis"),
    # Microbiology / Virology
    ("32623-1", "Hepatitis B virus surface Ag [Presence] in Serum", "Microbiology|Hepatitis"),
    ("13954-3", "Hepatitis B virus core Ab [Presence] in Serum", "Microbiology|Hepatitis"),
    ("13955-0", "Hepatitis B virus DNA [#/volume] in Serum by NAA with probe detection", "Microbiology|Hepatitis"),
    ("11259-9", "Hepatitis C virus Ab [Presence] in Serum", "Microbiology|Hepatitis"),
    ("38180-6", "HIV 1+2 Ab+HIV1 p24 Ag [Presence] in Serum or Plasma", "Microbiology|Viral"),
    ("94500-6", "SARS-CoV-2 (COVID-19) RNA [Presence] in Respiratory specimen by NAA", "Microbiology|Viral"),
    # Imaging / panels
    ("24323-8", "Comprehensive metabolic 2000 panel - Serum or Plasma", "Panels"),
    ("57021-8", "CBC W Auto Differential panel - Blood", "Panels"),
    ("57022-6", "CBC W Differential panel - Blood", "Panels"),
    ("24320-4", "Basic metabolic 1998 panel - Serum or Plasma", "Panels"),
    ("57698-3", "Lipid panel with direct LDL - Serum or Plasma", "Panels"),
    ("24356-8", "Urinalysis complete panel - Urine", "Panels"),
    ("24357-6", "Urinalysis microscopic panel - Urine", "Panels"),
    # Cardiology / pulmonary measures
    ("8867-4", "Heart rate", "Vital signs"),
    ("8480-6", "Systolic blood pressure", "Vital signs"),
    ("8462-4", "Diastolic blood pressure", "Vital signs"),
    ("8310-5", "Body temperature", "Vital signs"),
    ("9279-1", "Respiratory rate", "Vital signs"),
    ("2710-2", "Oxygen saturation in Arterial blood by Pulse oximetry", "Vital signs"),
    ("8302-2", "Body height", "Anthropometric"),
    ("29463-7", "Body weight", "Anthropometric"),
    ("39156-5", "Body mass index (BMI) [Ratio]", "Anthropometric"),
    ("8277-6", "Body surface area", "Anthropometric"),
    ("3137-7", "Body height measured", "Anthropometric"),
    ("3141-9", "Body weight measured", "Anthropometric"),
    # Tumour markers
    ("1986-9", "Alpha-1-fetoprotein [Mass/volume] in Serum or Plasma", "Chemistry|Tumor markers"),
    ("2030-5", "Carcinoembryonic Ag [Mass/volume] in Serum or Plasma", "Chemistry|Tumor markers"),
    ("83112-4", "CA 125 [Units/volume] in Serum or Plasma", "Chemistry|Tumor markers"),
    ("83113-2", "CA 19-9 [Units/volume] in Serum or Plasma", "Chemistry|Tumor markers"),
    ("83114-0", "CA 15-3 [Units/volume] in Serum or Plasma", "Chemistry|Tumor markers"),
    ("2857-1", "Prostate specific Ag [Mass/volume] in Serum or Plasma", "Chemistry|Tumor markers"),
    # Iron / B12 / folate
    ("2498-4", "Iron [Mass/volume] in Serum or Plasma", "Hematology|Iron studies"),
    ("2500-7", "Iron binding capacity [Mass/volume] in Serum or Plasma", "Hematology|Iron studies"),
    ("2501-5", "Iron saturation [Mass Fraction] in Serum or Plasma", "Hematology|Iron studies"),
    ("2276-4", "Ferritin [Mass/volume] in Serum or Plasma", "Hematology|Iron studies"),
    ("2132-9", "Vitamin B12 [Mass/volume] in Serum or Plasma", "Hematology|Vitamins"),
    ("2284-8", "Folate [Mass/volume] in Serum or Plasma", "Hematology|Vitamins"),
    ("1989-3", "25-Hydroxycholecalciferol [Mass/volume] in Serum or Plasma", "Endocrine|Vitamin D"),
    # ABG
    ("2019-8", "Carbon dioxide [Partial pressure] in Arterial blood", "Chemistry|Blood gas"),
    ("2703-7", "Oxygen [Partial pressure] in Arterial blood", "Chemistry|Blood gas"),
    ("2744-1", "pH of Arterial blood", "Chemistry|Blood gas"),
    ("1959-6", "Bicarbonate [Moles/volume] in Arterial blood", "Chemistry|Blood gas"),
    ("11556-8", "Base excess in Arterial blood", "Chemistry|Blood gas"),
    # Misc
    ("3187-2", "Coagulation factor II actual/normal in Platelet poor plasma", "Hematology|Coagulation"),
    ("13965-9", "Microscopic observation [Identifier] in Urine sediment", "Urinalysis"),
    ("3091-6", "Urate [Mass/volume] in Serum or Plasma", "Chemistry|Metabolic"),
    ("2885-2", "Total protein [Mass/volume] in Serum or Plasma", "Chemistry|Liver"),
    ("3091-6", "Uric acid [Mass/volume] in Serum or Plasma", "Chemistry|Metabolic"),
    ("32309-7", "Anion gap 4 in Serum or Plasma", "Chemistry|Electrolytes"),
    ("44963-7", "Estimated GFR by CKD-EPI formula", "Chemistry|Renal"),
    ("47532-7", "INR result interpretation", "Hematology|Coagulation"),
    ("2516-3", "Carbon dioxide, total [Moles/volume] in Serum or Plasma", "Chemistry|Electrolytes"),
    ("13965-9", "Microalbumin/Creatinine ratio (Albumin/Creatinine)", "Urinalysis"),
    ("13458-5", "Cholesterol, non-HDL [Mass/volume] in Serum or Plasma", "Chemistry|Lipids"),
    ("3026-2", "Thyroxine (T4) total [Mass/volume] in Serum or Plasma", "Endocrine|Thyroid"),
    ("3053-6", "Triiodothyronine (T3) total [Mass/volume] in Serum or Plasma", "Endocrine|Thyroid"),
    ("8061-4", "Adrenocorticotropin [Mass/volume] in Plasma", "Endocrine|Pituitary"),
    ("2143-6", "Cortisol [Mass/volume] in Serum or Plasma", "Endocrine|Adrenal"),
    ("83001-9", "Vitamin D 25 hydroxy total [Mass/volume]", "Endocrine|Vitamin D"),
    ("2218-6", "Insulin [Units/volume] in Serum or Plasma", "Endocrine|Diabetes"),
    ("1492-8", "Glucose [Mass/volume] in 2 hour post 75 g glucose PO Serum or Plasma", "Endocrine|Diabetes"),
    ("32483-0", "Hemoglobin A1c (NGSP)", "Endocrine|Diabetes"),
    ("32484-8", "Hemoglobin A1c (IFCC)", "Endocrine|Diabetes"),
    # Pharmacology – therapeutic drug monitoring
    ("3380-3", "Digoxin [Mass/volume] in Serum or Plasma", "TDM|Cardiac"),
    ("3431-4", "Lithium [Moles/volume] in Serum or Plasma", "TDM|Mental"),
    ("4049-3", "Valproate [Mass/volume] in Serum or Plasma", "TDM|Neurology"),
    ("3948-7", "Phenytoin [Mass/volume] in Serum or Plasma", "TDM|Neurology"),
    ("3382-9", "Carbamazepine [Mass/volume] in Serum or Plasma", "TDM|Neurology"),
    ("3493-4", "Theophylline [Mass/volume] in Serum or Plasma", "TDM|Respiratory"),
    ("4023-8", "Tacrolimus [Mass/volume] in Blood", "TDM|Immunosuppressant"),
    ("4022-0", "Sirolimus [Mass/volume] in Blood", "TDM|Immunosuppressant"),
    ("3974-3", "Cyclosporine [Mass/volume] in Blood", "TDM|Immunosuppressant"),
    ("3717-6", "Methotrexate [Mass/volume] in Serum or Plasma", "TDM|Oncology"),
    ("3987-5", "Mycophenolate [Mass/volume] in Serum or Plasma", "TDM|Immunosuppressant"),
    ("3548-5", "Gentamicin [Mass/volume] in Serum or Plasma trough", "TDM|Antibiotics"),
    ("3672-3", "Vancomycin trough [Mass/volume] in Serum or Plasma", "TDM|Antibiotics"),
    # Toxicology
    ("5630-9", "Ethanol [Mass/volume] in Blood", "Toxicology"),
    ("5640-8", "Salicylates [Mass/volume] in Serum or Plasma", "Toxicology"),
    ("3899-2", "Acetaminophen [Mass/volume] in Serum or Plasma", "Toxicology"),
    ("3596-4", "Lead [Mass/volume] in Blood", "Toxicology|Heavy metals"),
    # Microbiology – common cultures
    ("600-7", "Bacteria identified in Blood by Culture", "Microbiology|Culture"),
    ("630-4", "Bacteria identified in Urine by Culture", "Microbiology|Culture"),
    ("6463-4", "Bacteria identified in Sputum by Culture", "Microbiology|Culture"),
    ("612-2", "Bacteria identified in Stool by Culture", "Microbiology|Culture"),
    ("17928-3", "Sensitivity testing by Disk diffusion", "Microbiology|Susceptibility"),
    # Viral serology / nucleic acid
    ("13950-1", "Hepatitis B virus surface Ab [Presence] in Serum", "Microbiology|Hepatitis"),
    ("16128-1", "Hepatitis A virus IgM Ab [Presence] in Serum", "Microbiology|Hepatitis"),
    ("13952-7", "Hepatitis B virus e Ag [Presence] in Serum", "Microbiology|Hepatitis"),
    ("13955-0", "HCV RNA [#/volume] in Serum or Plasma by NAA", "Microbiology|Hepatitis"),
    ("48159-8", "HIV 1 RNA [#/volume] (viral load) in Plasma by NAA", "Microbiology|Viral"),
    ("49473-1", "Epstein Barr virus DNA [#/volume] in Plasma by NAA", "Microbiology|Viral"),
    ("21626-7", "Cytomegalovirus DNA [#/volume] in Plasma by NAA", "Microbiology|Viral"),
    # Allergy / immunology
    ("19113-0", "IgE [Mass/volume] in Serum", "Immunology"),
    ("2458-8", "IgA [Mass/volume] in Serum or Plasma", "Immunology"),
    ("2465-3", "IgG [Mass/volume] in Serum or Plasma", "Immunology"),
    ("2472-9", "IgM [Mass/volume] in Serum or Plasma", "Immunology"),
    ("11572-5", "Complement C3 [Mass/volume] in Serum or Plasma", "Immunology"),
    ("4485-9", "Complement C4 [Mass/volume] in Serum or Plasma", "Immunology"),
    ("11580-8", "Antinuclear Ab [Titer] in Serum by Immunofluorescence", "Immunology|Autoimmune"),
    ("31041-7", "Anti-cyclic citrullinated peptide Ab [Mass/volume] in Serum", "Immunology|Autoimmune"),
    ("11572-5", "Rheumatoid factor [Mass/volume] in Serum or Plasma", "Immunology|Autoimmune"),
    # Cardiac / inflammation
    ("30934-4", "Troponin T.cardiac [Mass/volume] in Serum or Plasma", "Chemistry|Cardiac"),
    ("89579-7", "High sensitivity troponin I [Mass/volume] in Serum or Plasma", "Chemistry|Cardiac"),
    ("30341-2", "Erythrocyte sedimentation rate by Wintrobe", "Hematology|Inflammation"),
    ("76770-3", "High sensitivity CRP [Mass/volume] in Serum or Plasma", "Chemistry|Inflammation"),
    # Reproductive / pregnancy
    ("2106-3", "Chorionic gonadotropin [Units/volume] in Serum or Plasma", "Endocrine|Pregnancy"),
    ("19080-1", "Estradiol panel - Serum or Plasma", "Endocrine|Pregnancy"),
    ("2842-3", "Prolactin [Mass/volume]", "Endocrine|Pregnancy"),
    # Acid-base / lactate
    ("3045-2", "Lactate [Moles/volume] in Arterial blood", "Chemistry|Blood gas"),
    ("32554-8", "Base excess in Venous blood", "Chemistry|Blood gas"),
    # Hematology – special
    ("33037-3", "Haptoglobin [Mass/volume] in Serum or Plasma", "Hematology|Iron studies"),
    ("4679-7", "Reticulocytes [#/volume] in Blood", "Hematology|CBC"),
    ("8625-6", "Reticulocyte/100 erythrocytes in Blood", "Hematology|CBC"),
    ("38483-4", "Creatinine [Mass/volume] in Body fluid", "Chemistry|Other"),
    # Imaging order codes – common modalities
    ("36643-5", "XR Chest 2 Views", "Imaging|X-ray"),
    ("30746-2", "CT Head W/O contrast", "Imaging|CT"),
    ("30621-7", "CT Chest W/O contrast", "Imaging|CT"),
    ("30577-1", "CT Abdomen W/O contrast", "Imaging|CT"),
    ("24590-2", "MRI Brain W/O contrast", "Imaging|MRI"),
    ("36849-8", "MRI Lumbar spine W/O contrast", "Imaging|MRI"),
    ("39127-6", "Echocardiography study", "Imaging|US"),
    # ECG / pulmonary function
    ("11524-6", "Electrocardiogram (EKG)", "Diagnostic|ECG"),
    ("19868-9", "FEV1 (forced expiratory volume in 1 second)", "Diagnostic|Spirometry"),
    ("19870-5", "FVC (forced vital capacity)", "Diagnostic|Spirometry"),
    ("19926-5", "FEV1/FVC", "Diagnostic|Spirometry"),
    ("33452-4", "Predicted FEV1", "Diagnostic|Spirometry"),
    # Pharmacology / general
    ("1968-7", "Bilirubin.direct (conjugated)", "Chemistry|Liver"),
    ("1971-1", "Bilirubin.indirect (unconjugated)", "Chemistry|Liver"),
    ("32623-1", "Amylase [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Pancreatic"),
    ("1798-8", "Lipase [Enzymatic activity/volume] in Serum or Plasma", "Chemistry|Pancreatic"),
    # Pain / functional scores
    ("72514-3", "Pain severity - 0-10 verbal numeric rating", "Functional"),
    ("72172-0", "Mini-mental state examination score", "Functional"),
    # COVID-19 antibodies
    ("94762-2", "SARS-CoV-2 spike IgG Ab [Presence] in Serum", "Microbiology|Viral"),
    ("94504-8", "SARS-CoV-2 Ag [Presence] in Respiratory specimen", "Microbiology|Viral"),
    ("94531-1", "SARS-CoV-2 RNA panel - Respiratory specimen", "Microbiology|Viral"),
]
for c, t, h in LOINC_CORE:
    _loinc(c, t, h)


# ---------------------------------------------------------------- write csvs


def _write(rows: list[tuple[str, str, str]], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "term", "hierarchy"])
        seen: set[str] = set()
        for code, term, hier in rows:
            key = f"{code}|{term}"
            if key in seen:
                continue
            seen.add(key)
            w.writerow([code, term, hier])


def main() -> None:
    _write(ICD10, HERE / "icd10_simple.csv")
    _write([(c, t, h) for c, t, h in ATC], HERE / "atc_simple.csv")
    _write(LOINC, HERE / "loinc_minimal.csv")
    print(f"wrote {len(ICD10)} ICD-10, {len(ATC)} ATC, {len(LOINC)} LOINC rows")


if __name__ == "__main__":
    main()
