from pathlib import Path
from types import SimpleNamespace

from opticstream.cli.oct.watch import _MIN_FILE_SIZE_BYTES, OCTWatcherService
from opticstream.utils.filename_utils import extract_processed_index_from_filename


def _scan_config_for_mosaic3(grid_size_x: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        mosaics_per_slice=3,
        acquisition=SimpleNamespace(
            grid_size_x_normal=grid_size_x,
            tile_saving_type="spectral",
        ),
    )


def test_extract_processed_index_from_filename():
    assert extract_processed_index_from_filename("processed_0123.nii") == 123
    assert (
        extract_processed_index_from_filename("/x/y/spectral/processed_0007.nii") == 7
    )


def test_discover_three_mosaic_candidates_groups_by_derived_mosaic(tmp_path: Path):
    watch_root = tmp_path / "watch"
    spectral_dir = watch_root / "spectral"
    spectral_dir.mkdir(parents=True)

    for idx in range(1, 7):
        (spectral_dir / f"processed_{idx:04d}.nii").write_bytes(
            b"\0" * _MIN_FILE_SIZE_BYTES
        )
    (spectral_dir / "ignore_me.txt").write_text("nope", encoding="utf-8")

    service = OCTWatcherService(
        project_name="proj",
        folder_path=watch_root,
        project_base_path=str(tmp_path),
        mosaic_ranges=[(1, 9999)],
        slice_offset=0,
        batch_size=3,
        scan_config=_scan_config_for_mosaic3(grid_size_x=3),
        direct=True,
        force_resend=False,
    )

    candidates = service.discover_candidates()
    assert len(candidates) == 2

    by_source_mosaic = {c.source_mosaic_id: c for c in candidates}
    assert sorted(by_source_mosaic) == [1, 4]

    assert [p.name for p in by_source_mosaic[1].files] == [
        "processed_0001.nii",
        "processed_0002.nii",
        "processed_0003.nii",
    ]
    assert [p.name for p in by_source_mosaic[4].files] == [
        "processed_0004.nii",
        "processed_0005.nii",
        "processed_0006.nii",
    ]

    assert by_source_mosaic[1].logical_mosaic_id == 1
    assert by_source_mosaic[4].logical_mosaic_id == 4
    assert all(c.logical_batch == 1 for c in candidates)
