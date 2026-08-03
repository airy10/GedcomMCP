#!/usr/bin/env python3

"""This module contains constants used throughout the GedcomMCP server."""

# Performance and Search Constants
MAX_REASONABLE_DISTANCE = 100
DEFAULT_PAGE_SIZE = 100
BIRTH_YEAR_PROXIMITY_THRESHOLD = 500
CONNECTIVITY_CHECK_DEPTH = 50
DEFAULT_FUZZY_THRESHOLD = 80
DEFAULT_MAX_RESULTS = 50
MAX_PAGE_SIZE_PERSON_FAMILY = 1000
MAX_PAGE_SIZE_OTHERS = 500
DEFAULT_MAX_DISTANCE = 30
DEFAULT_MAX_DISTANCE_ALL_PATHS = 15
DEFAULT_MAX_PATHS = 10
DEFAULT_MAX_LEVEL = 20
DEFAULT_GENERATIONS = 3
DEFAULT_UPDATE_INTERVAL = 1000


EVENT_TYPES = {
    "BIRT": {"name": "Birth", "description": "The event when mortal life begins"},
    "DEAT": {"name": "Death", "description": "The event when mortal life terminates"},
    "MARR": {
        "name": "Marriage",
        "description": "A legal, common-law or customary event of creating a family unit",
    },
    "DIV": {
        "name": "Divorce",
        "description": "An event of dissolving a marriage through civil action",
    },
    "ANUL": {
        "name": "Annulment",
        "description": "Declaring a marriage void from the beginning",
    },
    "BAPM": {
        "name": "Baptism",
        "description": "The event of baptism, performed in infancy or later",
    },
    "CHR": {
        "name": "Christening",
        "description": "The religious event of baptising and/or naming a child",
    },
    "CONF": {
        "name": "Confirmation",
        "description": "The religious event of conferring the gift of the Holy Ghost",
    },
    "BARM": {
        "name": "Bar Mitzvah",
        "description": "The ceremonial event held when a Jewish boy reaches age 13",
    },
    "BASM": {
        "name": "Bas Mitzvah",
        "description": "The ceremonial event held when a Jewish girl reaches age 13",
    },
    "BLES": {
        "name": "Blessing",
        "description": "A religious event of bestowing divine care or intercession",
    },
    "ADOP": {
        "name": "Adoption",
        "description": "Creation of a legally approved child-parent relationship",
    },
    "CREM": {
        "name": "Cremation",
        "description": "Disposal of the remains of a person's body by fire",
    },
    "BURI": {
        "name": "Burial",
        "description": "The event of the proper disposing of the mortal remains",
    },
    "GRAD": {
        "name": "Graduation",
        "description": "An event of awarding educational diplomas or degrees",
    },
    "RETI": {
        "name": "Retirement",
        "description": "An event of exiting an occupational relationship",
    },
    "EMIG": {
        "name": "Emigration",
        "description": "An event of leaving one's homeland with the intent of residing elsewhere",
    },
    "IMMI": {
        "name": "Immigration",
        "description": "An event of entering into a new locality with the intent of residing there",
    },
    "NATU": {
        "name": "Naturalization",
        "description": "The event of obtaining citizenship",
    },
    "CENS": {
        "name": "Census",
        "description": "The event of the periodic count of the population",
    },
    "PROB": {
        "name": "Probate",
        "description": "An event of judicial determination of the validity of a will",
    },
    "WILL": {"name": "Will", "description": "A legal document treated as an event"},
    "ENGA": {
        "name": "Engagement",
        "description": "An event of recording or announcing an agreement to marry",
    },
    "MARB": {
        "name": "Marriage Bann",
        "description": "An official public notice given that two people intend to marry",
    },
    "MARL": {
        "name": "Marriage License",
        "description": "An event of obtaining a legal license to marry",
    },
    "MARC": {
        "name": "Marriage Contract",
        "description": "An event of recording a formal agreement of marriage",
    },
    "MARS": {
        "name": "Marriage Settlement",
        "description": "An event of creating an agreement between marriage partners",
    },
    "RESI": {
        "name": "Residence",
        "description": "The act of dwelling at an address for a period of time",
    },
    "OCCU": {
        "name": "Occupation",
        "description": "The type of work or profession of an individual",
    },
    "EDUC": {
        "name": "Education",
        "description": "Indicator of a level of education attained",
    },
    "RELI": {
        "name": "Religion",
        "description": "A religious denomination to which a person is affiliated",
    },
    "NATI": {
        "name": "Nationality",
        "description": "The national heritage of an individual",
    },
    "CAST": {
        "name": "Caste",
        "description": "The name of an individual's rank or status in society",
    },
    "TITL": {
        "name": "Title",
        "description": "A description of a specific writing or other work",
    },
    "PROP": {
        "name": "Property",
        "description": "Pertaining to possessions such as real estate or other property",
    },
    "NCHI": {
        "name": "Number of Children",
        "description": "The number of children that this person is known to be the parent",
    },
    "NMR": {
        "name": "Number of Marriages",
        "description": "The number of different families that this person was known to have been a member",
    },
    "EVEN": {
        "name": "Event",
        "description": "A noteworthy happening related to an individual, group, or organization",
    },
}

ATTRIBUTE_TYPES = {
    "CAST": {
        "name": "Caste",
        "description": "The name of an individual's rank or status in society",
    },
    "DSCR": {
        "name": "Description",
        "description": "The physical characteristics of a person, place, or thing",
    },
    "EDUC": {
        "name": "Education",
        "description": "Indicator of a level of education attained",
    },
    "IDNO": {
        "name": "Identity Number",
        "description": "A number assigned to identify a person within some significant external system",
    },
    "NATI": {
        "name": "Nationality",
        "description": "The national heritage of an individual",
    },
    "NCHI": {
        "name": "Number of Children",
        "description": "The number of children that this person is known to be the parent",
    },
    "NMR": {
        "name": "Number of Marriages",
        "description": "The number of different families that this person was known to have been a member",
    },
    "OCCU": {
        "name": "Occupation",
        "description": "The type of work or profession of an individual",
    },
    "PROP": {
        "name": "Property",
        "description": "Pertaining to possessions such as real estate or other property",
    },
    "RELI": {
        "name": "Religion",
        "description": "A religious denomination to which a person is affiliated",
    },
    "RESI": {
        "name": "Residence",
        "description": "The act of dwelling at an address for a period of time",
    },
    "SSN": {
        "name": "Social Security Number",
        "description": "A number assigned by the United States Social Security Administration",
    },
    "TITL": {
        "name": "Title",
        "description": "A description of a specific writing or other work",
    },
}

CUSTOM_TAG_TYPES = {
    "_CIRC": {"name": "Circumcision", "description": "Custom FTM fact: circumcision"},
    "_DCAUSE": {"name": "Cause of Death", "description": "Custom FTM fact: cause of death"},
    "_DEG": {"name": "Degree", "description": "Custom FTM fact: academic degree"},
    "_DEST": {"name": "Destination", "description": "Custom FTM fact: immigration/emigration destination"},
    "_DNA": {"name": "DNA Markers", "description": "Custom FTM fact: DNA markers"},
    "_ELEC": {"name": "Election", "description": "Custom FTM fact: election to office"},
    "_EMPLOY": {"name": "Employment/Occupation", "description": "Custom FTM fact: employment"},
    "_EXCM": {"name": "Excommunication", "description": "Custom FTM fact: excommunication"},
    "_FUN": {"name": "Funeral", "description": "Custom FTM fact: funeral"},
    "_HEIG": {"name": "Height", "description": "Custom FTM fact: height"},
    "_WEIG": {"name": "Weight", "description": "Custom FTM fact: weight"},
    "_INIT": {"name": "Initiatory (LDS)", "description": "Custom FTM fact: LDS initiatory ordinance"},
    "_MDCL": {"name": "Medical Condition", "description": "Custom FTM fact: medical condition"},
    "_MILT": {"name": "Military Service", "description": "Custom FTM fact: military service"},
    "_MILTID": {"name": "Military Serial Number", "description": "Custom FTM fact: military serial number"},
    "_MISN": {"name": "Mission (LDS)", "description": "Custom FTM fact: LDS mission"},
    "_ORDI": {"name": "Ordinance", "description": "Custom FTM fact: ordinance"},
    "_ORIG": {"name": "Origin", "description": "Custom FTM fact: origin"},
    "_SEPR": {"name": "Separation", "description": "Custom FTM fact: separation (valid under INDI or FAM)"},
    "_PHOTO": {"name": "Primary Photo", "description": "Custom FTM tag: flags default portrait OBJE"},
}

INDI_ONLY_CUSTOM_TAGS = {
    "_CIRC", "_DCAUSE", "_DEG", "_DEST", "_DNA", "_ELEC", "_EMPLOY",
    "_EXCM", "_FUN", "_HEIG", "_WEIG", "_INIT", "_MDCL", "_MILT",
    "_MILTID", "_MISN", "_ORDI", "_ORIG", "_PHOTO",
}
