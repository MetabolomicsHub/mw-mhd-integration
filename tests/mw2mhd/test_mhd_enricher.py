import json
from pathlib import Path

from mw2mhd import mhd_enricher


def test_enrich_mhd_file_backfills_summary_and_archive_raw_files(
    tmp_path: Path, monkeypatch
):
    mhd_path = tmp_path / "STTEST.mhd.json"
    mhd_data = {
        "graph": {
            "nodes": [
                {
                    "id": "study-1",
                    "type": "study",
                    "repository_identifier": "STTEST",
                    "title": "Example study",
                    "submission_date": "2025-04-04T00:00:00",
                    "public_release_date": "2025-04-04T00:00:00",
                }
            ],
            "relationships": [],
        }
    }
    mhd_path.write_text(json.dumps(mhd_data), encoding="utf-8")

    monkeypatch.setattr(
        mhd_enricher,
        "fetch_mw_study_summary",
        lambda study_id, data_path: {
            "study_id": study_id,
            "submission_date": "2025-04-04",
            "release_date": "2026-03-19",
            "license": "CC BY-NC-ND",
            "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en",
            "study_url": "https://www.metabolomicsworkbench.org/data/DRCCMetadata.php?StudyID=STTEST",
        },
    )
    monkeypatch.setattr(
        mhd_enricher,
        "fetch_mw_study_files",
        lambda study_id, data_path: {
            "study_id": study_id,
            "files": [
                "STTEST_archive.zip",
                "STTEST_notes.txt",
                "direct_file.mzML",
            ],
            "compressed_file_content": {
                "STTEST_archive.zip": [
                    {"name": "inside/sample1.raw", "size": 123},
                    {"name": "inside/sample1.txt", "size": 45},
                ]
            },
        },
    )

    result = mhd_enricher.enrich_mhd_file(mhd_path, data_path=tmp_path)
    enriched = json.loads(mhd_path.read_text(encoding="utf-8"))
    study = next(node for node in enriched["graph"]["nodes"] if node["type"] == "study")
    raw_nodes = [
        node for node in enriched["graph"]["nodes"] if node.get("type") == "raw-data-file"
    ]

    assert result["updated"] is True
    assert study["public_release_date"] == "2026-03-19T00:00:00"
    assert study["license"] == "https://creativecommons.org/licenses/by-nc-nd/4.0/deed.en"
    assert len(raw_nodes) == 2
    names = {node["name"] for node in raw_nodes}
    assert names == {"direct_file.mzML", "inside/sample1.raw"}

    archive_member = next(node for node in raw_nodes if node["name"] == "inside/sample1.raw")
    assert archive_member["url_list"] == [
        "https://dashboard.gnps2.org/?usi=mzspec:STTEST:inside/sample1.raw",
        "https://www.metabolomicsworkbench.org/studydownload/STTEST_archive.zip",
    ]
