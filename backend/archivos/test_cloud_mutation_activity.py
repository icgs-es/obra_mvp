from unittest.mock import (
    Mock,
    patch,
)

from django.contrib.auth import (
    get_user_model,
)
from django.contrib.auth.models import (
    Group,
    Permission,
)
from django.contrib.messages.storage.session import (
    SessionStorage,
)
from django.test import (
    RequestFactory,
    TestCase,
)

from actividad.models import (
    ActividadPlataforma,
)
from archivos.cloud_activity import (
    registrar_operacion_cloud,
    snapshot_cloud_references,
)
from archivos.cloud_actions import (
    cloud_item_delete,
    cloud_item_move,
    cloud_item_rename,
)
from archivos.cloud_views import (
    cloud_folder_create,
)
from archivos.models import (
    Archivo,
    Carpeta,
    ReglaAccesoRaizCloud,
)
from usuarios.models import Team


class CloudMutationActivityTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username="cloud_actor",
                password="x",
                is_staff=False,
            )
        )

        # ARCHIVOS_CLOUD_ACTIONS_RBAC_V1A_R5
        #
        # Los tests de actividad documental deben
        # representar el contrato real:
        #
        #   permiso funcional + ámbito documental.
        #
        # El estado staff no forma parte de la
        # autorización de INTASA Documents.

        self.document_group = Group.objects.create(
            name="Cloud Mutation Documents",
        )

        self.user.groups.add(
            self.document_group
        )


        for root_name in (
            "TECNICOS",
            "FORMACION",
        ):
            rule = (
                ReglaAccesoRaizCloud.objects
                .create(
                    nombre_raiz=root_name,
                    activa=True,
                )
            )

            rule.grupos.add(
                self.document_group
            )


        required_permissions = (
            "add_archivo",
            "add_carpeta",
            "change_archivo",
            "change_carpeta",
            "delete_archivo",
            "delete_carpeta",
        )


        permissions = list(
            Permission.objects.filter(
                content_type__app_label="archivos",
                codename__in=(
                    required_permissions
                ),
            )
        )


        assert len(permissions) == len(
            required_permissions
        )


        self.user.user_permissions.add(
            *permissions
        )


        self.team = Team.objects.create(
            name="Cloud Team",
        )

        self.other_team = (
            Team.objects.create(
                name="Other Cloud Team",
            )
        )

        self.user.teams.add(
            self.team,
            self.other_team,
        )

        self.cloud_folder = (
            Carpeta.objects.create(
                team=None,
                nombre="Cloud index",
                slug="archivos",
                owner=self.user,
                visibilidad="PRIVADA",
            )
        )

        self.factory = RequestFactory()

    def request(self, path, data):
        request = self.factory.post(
            path,
            data=data,
        )

        request.user = self.user
        request.session = {
            "active_team_id": str(
                self.team.pk
            ),
        }

        request._messages = (
            SessionStorage(request)
        )

        return request

    def reference(
        self,
        *,
        path,
        team=None,
        name=None,
    ):
        name = (
            name
            or path.rsplit("/", 1)[-1]
        )

        return Archivo.objects.create(
            team=team,
            carpeta=self.cloud_folder,
            fichero="",
            nombre_original=name,
            nombre_logico=name,
            descripcion="",
            subido_por=self.user,
            storage_provider="nextcloud",
            storage_key=path,
            storage_object_id=(
                f"remote-{Archivo.objects.count() + 1}"
            ),
        )

    def fake_gateway(self):
        gateway = Mock()

        gateway.normalize_path.side_effect = (
            lambda value, allow_empty=True:
            str(value or "").strip("/")
        )

        gateway.normalize_name.side_effect = (
            lambda value:
            str(value or "").strip()
        )

        return gateway

    def test_snapshot_single_team(
        self,
    ):
        self.reference(
            path="TECNICOS/a.pdf",
            team=self.team,
        )

        snapshot = (
            snapshot_cloud_references(
                "TECNICOS"
            )
        )

        self.assertEqual(
            snapshot["reference_count"],
            1,
        )

        self.assertEqual(
            snapshot["assigned_team_ids"],
            [self.team.pk],
        )

        self.assertEqual(
            snapshot["resolved_team"],
            self.team,
        )

    def test_mixed_snapshot_is_private(
        self,
    ):
        self.reference(
            path="FORMACION/a.pdf",
            team=self.team,
        )

        self.reference(
            path="FORMACION/b.pdf",
            team=None,
        )

        snapshot = (
            snapshot_cloud_references(
                "FORMACION"
            )
        )

        request = self.request(
            "/app/archivos/cloud/renombrar/",
            {},
        )

        registrar_operacion_cloud(
            request=request,
            accion="renombrar",
            item={
                "name": "FORMACION",
                "is_folder": True,
            },
            source="FORMACION",
            destination="FORMACION-NUEVA",
            snapshot=snapshot,
            references_affected=2,
            url="/app/archivos/",
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertIsNone(
            activity.team_id
        )

        self.assertEqual(
            activity.visibilidad,
            (
                ActividadPlataforma
                .Visibilidad
                .ACTOR
            ),
        )

        self.assertEqual(
            activity.metadata[
                "team_resolution"
            ],
            (
                "mixed_or_unclassified_"
                "references"
            ),
        )

    @patch(
        "archivos.cloud_views."
        "NextcloudCloudGateway"
    )
    def test_create_folder_activity(
        self,
        gateway_class,
    ):
        gateway = self.fake_gateway()

        gateway.create_directory.return_value = {
            "name": "NUEVA",
            "storage_key": (
                "TECNICOS/NUEVA"
            ),
            "is_folder": True,
            "file_id": "",
            "etag": "folder-etag",
        }

        gateway_class.return_value = gateway

        response = cloud_folder_create(
            self.request(
                (
                    "/app/archivos/"
                    "cloud/carpeta/nueva/"
                ),
                {
                    "path": "TECNICOS",
                    "name": "NUEVA",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.accion,
            "crear_carpeta",
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.metadata[
                "storage_provider"
            ],
            "nextcloud",
        )

    @patch(
        "archivos.cloud_actions."
        "_is_protected_root",
        return_value=False,
    )
    @patch(
        "archivos.cloud_actions."
        "NextcloudCloudGateway"
    )
    def test_rename_file_activity(
        self,
        gateway_class,
        _protected,
    ):
        reference = self.reference(
            path="TECNICOS/viejo.pdf",
            team=self.team,
            name="viejo.pdf",
        )

        gateway = self.fake_gateway()

        gateway.get_item.return_value = {
            "name": "viejo.pdf",
            "is_folder": False,
            "file_id": "remote-1",
            "etag": "old-etag",
        }

        gateway.move_path.return_value = {
            "name": "nuevo.pdf",
            "storage_key": (
                "TECNICOS/nuevo.pdf"
            ),
            "is_folder": False,
            "file_id": "remote-1",
            "etag": "new-etag",
        }

        gateway_class.return_value = gateway

        response = cloud_item_rename(
            self.request(
                (
                    "/app/archivos/"
                    "cloud/renombrar/"
                ),
                {
                    "path": (
                        "TECNICOS/viejo.pdf"
                    ),
                    "name": "nuevo.pdf",
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        reference.refresh_from_db()

        self.assertEqual(
            reference.storage_key,
            "TECNICOS/nuevo.pdf",
        )

        self.assertEqual(
            reference.nombre_original,
            "nuevo.pdf",
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.accion,
            "renombrar",
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

    @patch(
        "archivos.cloud_actions."
        "_validate_destination_parent",
        return_value="FORMACION",
    )
    @patch(
        "archivos.cloud_actions."
        "_is_protected_root",
        return_value=False,
    )
    @patch(
        "archivos.cloud_actions."
        "NextcloudCloudGateway"
    )
    def test_move_file_activity(
        self,
        gateway_class,
        _protected,
        _destination,
    ):
        reference = self.reference(
            path="TECNICOS/mover.pdf",
            team=self.team,
            name="mover.pdf",
        )

        gateway = self.fake_gateway()

        gateway.get_item.return_value = {
            "name": "mover.pdf",
            "is_folder": False,
            "file_id": "remote-2",
            "etag": "old-etag",
        }

        gateway.move_path.return_value = {
            "name": "mover.pdf",
            "storage_key": (
                "FORMACION/mover.pdf"
            ),
            "is_folder": False,
            "file_id": "remote-2",
            "etag": "new-etag",
        }

        gateway_class.return_value = gateway

        response = cloud_item_move(
            self.request(
                (
                    "/app/archivos/"
                    "cloud/mover/"
                ),
                {
                    "path": (
                        "TECNICOS/mover.pdf"
                    ),
                    "destination_path": (
                        "FORMACION"
                    ),
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        reference.refresh_from_db()

        self.assertEqual(
            reference.storage_key,
            "FORMACION/mover.pdf",
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.accion,
            "mover",
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.metadata[
                "references_affected"
            ],
            1,
        )

    @patch(
        "archivos.cloud_actions."
        "_is_protected_root",
        return_value=False,
    )
    @patch(
        "archivos.cloud_actions."
        "NextcloudCloudGateway"
    )
    def test_delete_file_activity(
        self,
        gateway_class,
        _protected,
    ):
        reference = self.reference(
            path="TECNICOS/borrar.pdf",
            team=self.team,
            name="borrar.pdf",
        )

        reference_id = reference.pk

        gateway = self.fake_gateway()

        gateway.get_item.return_value = {
            "name": "borrar.pdf",
            "is_folder": False,
            "file_id": "remote-3",
            "etag": "old-etag",
        }

        gateway.delete_path.return_value = (
            None
        )

        gateway_class.return_value = gateway

        response = cloud_item_delete(
            self.request(
                (
                    "/app/archivos/"
                    "cloud/eliminar/"
                ),
                {
                    "path": (
                        "TECNICOS/borrar.pdf"
                    ),
                },
            )
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertFalse(
            Archivo.objects.filter(
                pk=reference_id
            ).exists()
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.accion,
            "eliminar",
        )

        self.assertEqual(
            activity.team,
            self.team,
        )

        self.assertEqual(
            activity.objeto_id,
            reference_id,
        )

        self.assertEqual(
            activity.metadata[
                "references_affected"
            ],
            1,
        )



class CloudVisibleMetadataTests(
    TestCase
):
    def setUp(self):
        self.user = (
            get_user_model()
            .objects.create_user(
                username=(
                    "cloud_visible_metadata"
                ),
                is_staff=True,
            )
        )

        self.team = Team.objects.create(
            name="Visible Metadata Team",
        )

        self.user.teams.add(
            self.team
        )

        self.cloud_folder = (
            Carpeta.objects.create(
                nombre="Cloud metadata index",
                slug="cloud-metadata-index",
                owner=self.user,
                visibilidad="PRIVADA",
            )
        )

        Archivo.objects.create(
            team=self.team,
            carpeta=self.cloud_folder,
            fichero="",
            nombre_original="parent-file.pdf",
            nombre_logico="parent-file.pdf",
            subido_por=self.user,
            storage_provider="nextcloud",
            storage_key=(
                "TECNICOS/parent-file.pdf"
            ),
            storage_object_id=(
                "metadata-remote-1"
            ),
        )

    def test_parent_references_are_not_visible_items(
        self,
    ):
        request = RequestFactory().post(
            (
                "/app/archivos/"
                "cloud/carpeta/nueva/"
            ),
            data={},
        )

        request.user = self.user
        request.session = {
            "active_team_id": str(
                self.team.pk
            ),
        }

        snapshot = (
            snapshot_cloud_references(
                "TECNICOS"
            )
        )

        registrar_operacion_cloud(
            request=request,
            accion="crear_carpeta",
            item={
                "name": "NUEVA",
                "storage_key": (
                    "TECNICOS/NUEVA"
                ),
                "is_folder": True,
                "file_id": "folder-1",
                "etag": "etag-1",
            },
            destination=(
                "TECNICOS/NUEVA"
            ),
            snapshot=snapshot,
            references_affected=0,
            url="/app/archivos/",
        )

        activity = (
            ActividadPlataforma
            .objects.get()
        )

        self.assertEqual(
            activity.metadata["nombres"],
            [],
        )

        self.assertEqual(
            activity.metadata[
                "affected_reference_names"
            ],
            [
                "parent-file.pdf",
            ],
        )

        self.assertNotIn(
            "parent-file.pdf",
            activity.descripcion,
        )
