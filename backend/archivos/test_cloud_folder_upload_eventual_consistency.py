from unittest.mock import Mock, patch

from django.conf import settings
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import SimpleTestCase

from .cloud_folder_upload import (
    FolderUploadInput,
    POLICY_SKIP,
    build_folder_upload_plan,
    execute_folder_upload,
)
from .cloud_gateway import (
    CloudGatewayError,
    NextcloudCloudGateway,
)


class _Response:
    status_code = 201

    def close(self):
        return None


class _ExistingGateway:
    def __init__(self):
        self.upload_calls = 0

    def path_exists(self, path):
        return True

    def get_item_eventually(self, path):
        return {
            "storage_key": path,
            "file_id": "9001",
            "size": 1,
            "etag": "etag-9001",
            "content_type": "text/plain",
            "is_folder": False,
        }

    def upload_file(self, parent, uploaded_file):
        self.upload_calls += 1

        raise AssertionError(
            "No debe repetirse el PUT "
            "cuando el archivo ya existe."
        )


class FolderUploadEventualConsistencyTests(
    SimpleTestCase
):
    def test_get_item_eventually_reintenta(self):
        gateway = object.__new__(
            NextcloudCloudGateway
        )

        with (
            patch.object(
                NextcloudCloudGateway,
                "get_item",
                side_effect=[
                    CloudGatewayError(
                        "Todavía no visible"
                    ),
                    CloudGatewayError(
                        "Todavía no visible"
                    ),
                    {
                        "storage_key": (
                            "Destino/a.txt"
                        ),
                        "file_id": "9001",
                    },
                ],
            ) as mocked_get,
            patch(
                "archivos.cloud_gateway.time.sleep"
            ) as mocked_sleep,
        ):
            item = gateway.get_item_eventually(
                "Destino/a.txt",
                attempts=4,
                initial_delay=0,
            )

        self.assertEqual(
            item["file_id"],
            "9001",
        )

        self.assertEqual(
            mocked_get.call_count,
            3,
        )

        mocked_sleep.assert_not_called()

    def test_upload_file_usa_lectura_eventual(self):
        gateway = object.__new__(
            NextcloudCloudGateway
        )

        gateway.normalize_path = (
            lambda value, allow_empty=True:
            str(value).strip("/")
        )

        gateway.normalize_name = (
            lambda value: str(value)
        )

        gateway.path_exists = (
            lambda path: False
        )

        gateway._request = Mock(
            return_value=_Response()
        )

        gateway.get_item_eventually = Mock(
            return_value={
                "storage_key": "Destino/a.txt",
                "file_id": "9001",
            }
        )

        uploaded = SimpleUploadedFile(
            "a.txt",
            b"x",
            content_type="text/plain",
        )

        item = NextcloudCloudGateway.upload_file(
            gateway,
            "Destino",
            uploaded,
        )

        self.assertEqual(
            item["file_id"],
            "9001",
        )

        gateway.get_item_eventually.assert_called_once_with(
            "Destino/a.txt"
        )

    def test_skip_reconcilia_sin_repetir_put(self):
        uploaded = SimpleUploadedFile(
            "a.txt",
            b"x",
            content_type="text/plain",
        )

        plan = build_folder_upload_plan(
            [
                FolderUploadInput(
                    uploaded_file=uploaded,
                    relative_path=(
                        "Proyecto/a.txt"
                    ),
                )
            ],
            destination_path="Destino",
        )

        gateway = _ExistingGateway()
        references = []

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            policy=POLICY_SKIP,
            reference_writer=(
                lambda planned, item, target:
                references.append({
                    "relative_path": (
                        planned.relative_path
                    ),
                    "file_id": item["file_id"],
                    "target": target,
                })
            ),
        )

        self.assertEqual(
            gateway.upload_calls,
            0,
        )

        self.assertEqual(
            len(references),
            1,
        )

        self.assertEqual(
            references[0]["file_id"],
            "9001",
        )

        self.assertEqual(
            result.file_results[0].status,
            "skipped",
        )

        self.assertEqual(
            result.file_results[
                0
            ].reference_error,
            "",
        )

    def test_javascript_trata_reference_error_como_error(
        self,
    ):
        from pathlib import Path

        path = (
            Path(settings.BASE_DIR)
            / "archivos"
            / "static"
            / "archivos"
            / "cloud_folder_upload_execute.js"
        )

        source = path.read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "P2B2_REFERENCE_ERROR_STATUS",
            source,
        )

        self.assertIn(
            'item.reference_error || ""',
            source,
        )
