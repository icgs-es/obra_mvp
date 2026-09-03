from __future__ import annotations

import json

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import (
    SimpleUploadedFile,
)
from django.test import TestCase
from django.urls import reverse

from actividad.models import (
    ActividadPlataforma,
)
from archivos.models import (
    Archivo,
    Carpeta,
)
from usuarios.models import Team


class FakeEndpointGateway:
    def __init__(self):
        self.items = {
            "EMPRESA": "directory",
            "EMPRESA/DESTINO": "directory",
        }
        self.upload_count = 0
        self.created = []
        self.uploaded = []
        self.deleted = []
        self.moved = []

    @staticmethod
    def normalize_path(
        value,
        allow_empty=True,
    ):
        path = str(value or "").replace(
            "\\",
            "/",
        ).strip("/")

        if not path and not allow_empty:
            raise RuntimeError(
                "Ruta vacía no permitida."
            )

        if any(
            part in {"", ".", ".."}
            for part in path.split("/")
            if path
        ):
            raise RuntimeError(
                "Ruta no válida."
            )

        return path

    def path_exists(self, path):
        return path in self.items

    def get_item(self, path):
        kind = self.items.get(path)

        if kind is None:
            raise RuntimeError("No existe")

        return {
            "storage_key": path,
            "name": path.rsplit("/", 1)[-1],
            "is_folder": (
                kind == "directory"
            ),
            "file_id": (
                ""
                if kind == "directory"
                else f"id-{path}"
            ),
            "etag": f"etag-{path}",
            "size": 1,
            "content_type": "text/plain",
        }

    def create_directory(
        self,
        parent_path,
        name,
    ):
        target = "/".join(
            part
            for part in (
                parent_path,
                name,
            )
            if part
        )

        if target in self.items:
            raise RuntimeError(
                "Ya existe."
            )

        self.items[target] = "directory"
        self.created.append(target)

        return self.get_item(target)

    def upload_file(
        self,
        parent_path,
        uploaded_file,
    ):
        target = "/".join(
            part
            for part in (
                parent_path,
                uploaded_file.name,
            )
            if part
        )

        if target in self.items:
            raise RuntimeError(
                "Ya existe."
            )

        self.upload_count += 1
        self.items[target] = "file"
        self.uploaded.append(target)

        return {
            "storage_key": target,
            "name": uploaded_file.name,
            "is_folder": False,
            "file_id": (
                f"remote-{self.upload_count}"
            ),
            "etag": (
                f"etag-{self.upload_count}"
            ),
            "size": uploaded_file.size,
            "content_type": (
                uploaded_file.content_type
            ),
        }

    def delete_path(self, path):
        del self.items[path]
        self.deleted.append(path)

    def move_path(
        self,
        source_path,
        destination_path,
    ):
        self.items[destination_path] = (
            self.items.pop(source_path)
        )
        self.moved.append(
            (
                source_path,
                destination_path,
            )
        )

        return self.get_item(
            destination_path
        )


class CloudFolderUploadEndpointTests(
    TestCase
):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            username="folder_upload_staff",
            password="x",
            is_staff=True,
        )

        self.other_user = (
            User.objects.create_user(
                username="folder_upload_other",
                password="x",
                is_staff=True,
            )
        )

        self.normal_user = (
            User.objects.create_user(
                username="folder_upload_normal",
                password="x",
            )
        )

        self.team = Team.objects.create(
            name="Empresa carpeta",
        )

        for user in (
            self.user,
            self.other_user,
            self.normal_user,
        ):
            user.teams.add(self.team)

        Carpeta.objects.create(
            nombre="Índice cloud",
            slug="intasa-cloud-system",
            owner=self.user,
            visibilidad="GLOBAL",
        )

        self.preflight_url = reverse(
            "archivos:"
            "cloud_folder_upload_preflight"
        )

        self.execute_url = reverse(
            "archivos:"
            "cloud_folder_upload_execute"
        )

        self.gateway = (
            FakeEndpointGateway()
        )

        self.login(self.user)

        # P3_TEST_FOLDER_UPLOAD_PERMISSION
        from django.contrib.auth.models import (
            Permission,
        )

        upload_folder_permission = (
            Permission.objects.get(
                content_type__app_label=(
                    "archivos"
                ),
                codename="upload_folder",
            )
        )


        for permission_user in (
            get_user_model()
            .objects
            .filter(is_staff=True)
        ):
            permission_user.user_permissions.add(
                upload_folder_permission
            )

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_team_id"] = str(
            self.team.pk
        )
        session.save()

    def preflight(
        self,
        *,
        policy="skip",
        files=None,
        directories=None,
        allow_replace=False,
    ):
        payload = {
            "path": "EMPRESA/DESTINO",
            "policy": policy,
            "allow_replace": (
                allow_replace
            ),
            "files": files or [
                {
                    "relative_path": (
                        "Proyecto/documento.txt"
                    ),
                    "size": 1,
                }
            ],
            "directories": (
                directories or []
            ),
        }

        return self.client.post(
            self.preflight_url,
            secure=True,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def execute(
        self,
        preflight_data,
        *,
        relative_path=(
            "Proyecto/documento.txt"
        ),
        finalize=False,
        content=b"x",
    ):
        return self.client.post(
            self.execute_url,
            secure=True,
            data={
                "token": (
                    preflight_data["token"]
                ),
                "manifest": json.dumps(
                    preflight_data[
                        "manifest"
                    ]
                ),
                "files": [
                    SimpleUploadedFile(
                        "documento.txt",
                        content,
                        content_type=(
                            "text/plain"
                        ),
                    )
                ],
                "relpath": [
                    relative_path
                ],
                "finalize": (
                    "1"
                    if finalize
                    else "0"
                ),
            },
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_preflight_devuelve_token_y_resumen(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        response = self.preflight()

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertTrue(data["ok"])
        self.assertTrue(
            data["can_execute"]
        )
        self.assertTrue(data["token"])
        self.assertEqual(
            data["summary"]["files"],
            1,
        )
        self.assertEqual(
            data["summary"][
                "root_name"
            ],
            "Proyecto",
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_reconoce_is_folder_del_gateway_real(
        self,
        gateway_class,
    ):
        self.gateway.items[
            "EMPRESA/DESTINO/Proyecto"
        ] = "directory"

        gateway_class.return_value = (
            self.gateway
        )

        response = self.preflight()

        self.assertEqual(
            response.status_code,
            200,
        )
        self.assertTrue(
            response.json()["ok"]
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_usuario_no_staff_denegado(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        self.login(self.normal_user)

        response = self.preflight()

        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertEqual(
            response.json()["error"][
                "code"
            ],
            "permission_denied",
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_preflight_rechaza_escape_parent(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        response = self.preflight(
            files=[
                {
                    "relative_path": (
                        "Proyecto/../secreto.txt"
                    ),
                    "size": 1,
                }
            ]
        )

        self.assertEqual(
            response.status_code,
            400,
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_execute_crea_referencia_y_actividad(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        preflight = (
            self.preflight().json()
        )

        response = self.execute(
            preflight,
            finalize=True,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertTrue(data["ok"])
        self.assertEqual(
            data["result"][
                "uploaded_files"
            ],
            1,
        )
        self.assertEqual(
            Archivo.objects.count(),
            1,
        )
        self.assertEqual(
            Archivo.objects.get().team,
            self.team,
        )
        self.assertTrue(
            data["activity_registered"]
        )
        self.assertEqual(
            ActividadPlataforma
            .objects.count(),
            1,
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_archivo_no_firmado_es_rechazado(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        preflight = (
            self.preflight().json()
        )

        response = self.execute(
            preflight,
            relative_path=(
                "Proyecto/otro.txt"
            ),
        )

        self.assertEqual(
            response.status_code,
            400,
        )
        self.assertEqual(
            response.json()["error"][
                "code"
            ],
            "unsigned_file",
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_token_no_puede_usarlo_otro_usuario(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        preflight = (
            self.preflight().json()
        )

        self.login(self.other_user)

        response = self.execute(
            preflight
        )

        self.assertEqual(
            response.status_code,
            403,
        )
        self.assertEqual(
            response.json()["error"][
                "code"
            ],
            "token_user_mismatch",
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_rename_preasignado_es_reintentable(
        self,
        gateway_class,
    ):
        self.gateway.items.update({
            (
                "EMPRESA/DESTINO/"
                "Proyecto"
            ): "directory",
            (
                "EMPRESA/DESTINO/"
                "Proyecto/documento.txt"
            ): "file",
        })

        gateway_class.return_value = (
            self.gateway
        )

        preflight = self.preflight(
            policy="rename"
        ).json()

        signed_file = (
            preflight["manifest"][
                "files"
            ][0]
        )

        self.assertEqual(
            signed_file["target_path"],
            (
                "EMPRESA/DESTINO/"
                "Proyecto/documento (1).txt"
            ),
        )

        first = self.execute(
            preflight
        )

        self.assertEqual(
            first.status_code,
            200,
        )
        self.assertEqual(
            self.gateway.upload_count,
            1,
        )

        second = self.execute(
            preflight
        )

        self.assertEqual(
            second.status_code,
            200,
        )
        self.assertEqual(
            self.gateway.upload_count,
            1,
        )
        self.assertEqual(
            second.json()["result"][
                "skipped_files"
            ],
            1,
        )

    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_ejecucion_multilote_finaliza_una_actividad(
        self,
        gateway_class,
    ):
        gateway_class.return_value = (
            self.gateway
        )

        files = [
            {
                "relative_path": (
                    "Proyecto/a.txt"
                ),
                "size": 1,
            },
            {
                "relative_path": (
                    "Proyecto/b.txt"
                ),
                "size": 1,
            },
        ]

        preflight = self.preflight(
            files=files,
        ).json()

        indexed_ids = []
        created_folders = set()

        for filename in (
            "a.txt",
            "b.txt",
        ):
            relative_path = (
                "Proyecto/"
                + filename
            )

            response = self.client.post(
                self.execute_url,
                secure=True,
                data={
                    "token": (
                        preflight["token"]
                    ),
                    "manifest": json.dumps(
                        preflight["manifest"]
                    ),
                    "files": [
                        SimpleUploadedFile(
                            filename,
                            b"x",
                            content_type=(
                                "text/plain"
                            ),
                        )
                    ],
                    "relpath": [
                        relative_path
                    ],
                    "directories": "[]",
                    "finalize": "0",
                },
            )

            self.assertEqual(
                response.status_code,
                200,
            )

            payload = response.json()

            self.assertTrue(
                payload["ok"]
            )

            indexed_ids.extend(
                payload[
                    "indexed_file_ids"
                ]
            )

            created_folders.update(
                payload["result"].get(
                    "created_folders",
                    [],
                )
            )

        final_response = self.client.post(
            self.execute_url,
            secure=True,
            data={
                "token": (
                    preflight["token"]
                ),
                "manifest": json.dumps(
                    preflight["manifest"]
                ),
                "directories": "[]",
                "finalize": "1",
                "activity_file_ids": (
                    json.dumps(
                        indexed_ids
                    )
                ),
                "created_folders_total": (
                    str(
                        len(created_folders)
                    )
                ),
            },
        )

        self.assertEqual(
            final_response.status_code,
            200,
        )

        final_payload = (
            final_response.json()
        )

        self.assertTrue(
            final_payload["ok"]
        )

        self.assertTrue(
            final_payload["finalized"]
        )

        self.assertTrue(
            final_payload[
                "activity_registered"
            ]
        )

        self.assertEqual(
            Archivo.objects.count(),
            2,
        )

        self.assertEqual(
            ActividadPlataforma
            .objects.count(),
            1,
        )


    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_retry_skip_reconcilia_referencia_perdida(
        self,
        gateway_class,
    ):
        gateway_class.return_value = self.gateway

        preflight = self.preflight().json()

        with patch(
            "archivos.cloud_folder_upload_views."
            "upsert_cloud_uploaded_reference",
            side_effect=RuntimeError(
                "Referencia temporalmente no disponible"
            ),
        ):
            first_response = self.execute(
                preflight,
                finalize=False,
            )

        self.assertEqual(
            first_response.status_code,
            200,
        )

        first_payload = first_response.json()
        first_file = (
            first_payload["result"]["files"][0]
        )

        self.assertEqual(
            first_file["status"],
            "uploaded",
        )

        self.assertTrue(
            first_file["reference_error"]
        )

        self.assertEqual(
            Archivo.objects.count(),
            0,
        )

        second_response = self.execute(
            preflight,
            finalize=True,
        )

        self.assertEqual(
            second_response.status_code,
            200,
        )

        second_payload = (
            second_response.json()
        )

        second_file = (
            second_payload["result"]["files"][0]
        )

        self.assertEqual(
            second_file["status"],
            "skipped",
        )

        self.assertFalse(
            second_file["reference_error"]
        )

        self.assertEqual(
            Archivo.objects.count(),
            1,
        )

        self.assertTrue(
            second_payload[
                "activity_registered"
            ]
        )


    @patch(
        "archivos.cloud_folder_upload_views."
        "NextcloudCloudGateway"
    )
    def test_cancelar_con_colision_no_emite_token(
        self,
        gateway_class,
    ):
        self.gateway.items.update({
            (
                "EMPRESA/DESTINO/"
                "Proyecto"
            ): "directory",
            (
                "EMPRESA/DESTINO/"
                "Proyecto/documento.txt"
            ): "file",
        })

        gateway_class.return_value = (
            self.gateway
        )

        response = self.preflight(
            policy="cancel"
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        data = response.json()

        self.assertFalse(
            data["can_execute"]
        )
        self.assertEqual(
            data["token"],
            "",
        )
