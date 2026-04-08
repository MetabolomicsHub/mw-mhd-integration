import json
from pathlib import Path

from mw2mhd.announcement_enricher import enrich_announcement_file


def test_enrich_announcement_file_adds_contact_emails_and_protocol_parameters(tmp_path: Path):
    mhd_path = tmp_path / "STTEST.mhd.json"
    announcement_path = tmp_path / "STTEST.announcement.json"

    mhd_data = {
        "graph": {
            "nodes": [
                {"id": "study-1", "type": "study"},
                {
                    "id": "person-1",
                    "type": "person",
                    "full_name": "Jane Example",
                    "email_list": ["jane@example.org"],
                },
                {
                    "id": "org-1",
                    "type": "organization",
                    "name": "Example Institute",
                },
                {
                    "id": "protocol-1",
                    "type": "protocol",
                    "name": "mass spectrometry",
                    "description": "MS protocol description",
                    "protocol_type_ref": "cv-protocol-type-1",
                },
                {
                    "id": "cv-protocol-type-1",
                    "type": "protocol-type",
                    "source": "CHMO",
                    "accession": "CHMO:0000470",
                    "name": "mass spectrometry",
                },
                {
                    "id": "param-def-1",
                    "type": "parameter-definition",
                    "name": "instrument name",
                    "parameter_type_ref": "cv-param-type-1",
                },
                {
                    "id": "cv-param-type-1",
                    "type": "parameter-type",
                    "source": "NCIT",
                    "accession": "NCIT:Cxxxxx",
                    "name": "instrument name",
                },
                {
                    "id": "cv-param-value-1",
                    "type": "parameter-value",
                    "source": "",
                    "accession": "",
                    "name": "Orbitrap Exploris",
                },
            ],
            "relationships": [
                {
                    "source_ref": "person-1",
                    "relationship_name": "submits",
                    "target_ref": "study-1",
                },
                {
                    "source_ref": "person-1",
                    "relationship_name": "affiliated-with",
                    "target_ref": "org-1",
                },
                {
                    "source_ref": "protocol-1",
                    "relationship_name": "has-protocol-definition",
                    "target_ref": "param-def-1",
                },
                {
                    "source_ref": "param-def-1",
                    "relationship_name": "has-instance",
                    "target_ref": "cv-param-value-1",
                },
            ],
        }
    }
    announcement_data = {
        "submitters": [{"full_name": "Jane Example"}],
        "protocols": [
            {
                "name": "mass spectrometry",
                "protocol_type": {
                    "source": "CHMO",
                    "accession": "CHMO:0000470",
                    "name": "mass spectrometry",
                },
            }
        ],
    }

    mhd_path.write_text(json.dumps(mhd_data), encoding="utf-8")
    announcement_path.write_text(json.dumps(announcement_data), encoding="utf-8")

    enrich_announcement_file(mhd_path, announcement_path)

    enriched = json.loads(announcement_path.read_text(encoding="utf-8"))
    assert enriched["submitters"][0]["email_list"] == ["jane@example.org"]
    assert enriched["submitters"][0]["affiliation_list"] == ["Example Institute"]
    assert enriched["protocols"][0]["description"] == "MS protocol description"
    assert enriched["protocols"][0]["protocol_parameters"] == [
        {
            "key": {
                "source": "NCIT",
                "accession": "NCIT:Cxxxxx",
                "name": "instrument name",
            },
            "values": [
                {
                    "source": "",
                    "accession": "",
                    "name": "Orbitrap Exploris",
                }
            ],
        }
    ]
