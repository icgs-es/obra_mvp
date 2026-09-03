from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from archivos.cloud_folder_upload import (
    FolderUploadInput,
    FolderUploadLimits,
    FolderUploadValidationError,
    POLICY_CANCEL,
    POLICY_RENAME,
    POLICY_REPLACE,
    POLICY_SKIP,
    build_folder_upload_plan,
    execute_folder_upload,
)


class FakeCloudGateway:
    def __init__(self):
        self.items = {
            "EMPRESA": "directory",
            "EMPRESA/DESTINO": "directory",
        }
        self.created = []
        self.uploaded = []
        self.deleted = []
        self.moved = []
        self.fail_upload_names = set()

    @staticmethod
    def normalize_path(value):
        return str(value or "").strip("/")

    def path_exists(self, path):
        return path in self.items

    def get_item(self, path):
        kind = self.items.get(path)

        if kind is None:
            raise RuntimeError("No existe")

        return {
            "storage_key": path,
            "name": path.rsplit("/", 1)[-1],
            "is_dir": kind == "directory",
            "type": kind,
        }

    def create_directory(self, parent_path, name):
        target = "/".join(
            part
            for part in (parent_path, name)
            if part
        )

        if target in self.items:
            raise RuntimeError("Ya existe")

        if (
            parent_path
            and self.items.get(parent_path) != "directory"
        ):
            raise RuntimeError("La carpeta padre no existe")

        self.items[target] = "directory"
        self.created.append(target)

        return {
            "storage_key": target,
            "name": name,
            "is_dir": True,
        }

    def upload_file(self, parent_path, uploaded_file):
        name = uploaded_file.name

        if name in self.fail_upload_names:
            raise RuntimeError(
                f"Fallo simulado para {name}"
            )

        target = "/".join(
            part
            for part in (parent_path, name)
            if part
        )

        if target in self.items:
            raise RuntimeError("El destino ya existe")

        if (
            parent_path
            and self.items.get(parent_path) != "directory"
        ):
            raise RuntimeError("La carpeta padre no existe")

        self.items[target] = "file"
        self.uploaded.append(target)

        return {
            "storage_key": target,
            "name": name,
            "is_dir": False,
            "size": uploaded_file.size,
        }

    def delete_path(self, path):
        if path not in self.items:
            raise RuntimeError("No existe")

        del self.items[path]
        self.deleted.append(path)

    def move_path(self, source_path, destination_path):
        if source_path not in self.items:
            raise RuntimeError("El origen no existe")

        if destination_path in self.items:
            raise RuntimeError("El destino ya existe")

        self.items[destination_path] = self.items.pop(
            source_path
        )
        self.moved.append(
            (source_path, destination_path)
        )

        return {
            "storage_key": destination_path,
            "name": destination_path.rsplit("/", 1)[-1],
        }


class CloudFolderUploadServiceTests(SimpleTestCase):
    destination = "EMPRESA/DESTINO"

    @staticmethod
    def upload(path, content=b"x"):
        return FolderUploadInput(
            uploaded_file=SimpleUploadedFile(
                path.rsplit("/", 1)[-1],
                content,
            ),
            relative_path=path,
        )

    def test_plan_conserva_estructura_anidada(self):
        plan = build_folder_upload_plan(
            [
                self.upload(
                    "Proyecto/documentos/informe.pdf",
                    b"1234",
                ),
                self.upload(
                    "Proyecto/imagenes/foto.jpg",
                    b"12",
                ),
            ],
            destination_path=self.destination,
        )

        self.assertEqual(plan.root_name, "Proyecto")
        self.assertEqual(plan.files_count, 2)
        self.assertEqual(plan.total_size, 6)

        self.assertEqual(
            plan.directories,
            (
                "EMPRESA/DESTINO/Proyecto",
                "EMPRESA/DESTINO/Proyecto/documentos",
                "EMPRESA/DESTINO/Proyecto/imagenes",
            ),
        )

    def test_rechaza_escape_parent(self):
        with self.assertRaises(
            FolderUploadValidationError
        ) as context:
            build_folder_upload_plan(
                [
                    self.upload(
                        "Proyecto/../secreto.txt"
                    )
                ],
                destination_path=self.destination,
            )

        self.assertEqual(
            context.exception.code,
            "invalid_component",
        )

    def test_rechaza_rutas_absolutas_y_unidades(self):
        for path in (
            "/Proyecto/fichero.txt",
            r"C:\Proyecto\fichero.txt",
        ):
            with self.subTest(path=path):
                with self.assertRaises(
                    FolderUploadValidationError
                ) as context:
                    build_folder_upload_plan(
                        [self.upload(path)],
                        destination_path=self.destination,
                    )

                self.assertEqual(
                    context.exception.code,
                    "absolute_path",
                )

    def test_rechaza_varias_carpetas_raiz(self):
        with self.assertRaises(
            FolderUploadValidationError
        ) as context:
            build_folder_upload_plan(
                [
                    self.upload("Uno/a.txt"),
                    self.upload("Dos/b.txt"),
                ],
                destination_path=self.destination,
            )

        self.assertEqual(
            context.exception.code,
            "multiple_roots",
        )

    def test_limite_numero_archivos(self):
        limits = FolderUploadLimits(max_files=1)

        with self.assertRaises(
            FolderUploadValidationError
        ) as context:
            build_folder_upload_plan(
                [
                    self.upload("Proyecto/a.txt"),
                    self.upload("Proyecto/b.txt"),
                ],
                destination_path=self.destination,
                limits=limits,
            )

        self.assertEqual(
            context.exception.code,
            "file_count_exceeded",
        )

    def test_limite_individual_y_total(self):
        with self.assertRaises(
            FolderUploadValidationError
        ) as context:
            build_folder_upload_plan(
                [
                    self.upload(
                        "Proyecto/grande.bin",
                        b"123456",
                    )
                ],
                destination_path=self.destination,
                limits=FolderUploadLimits(
                    max_file_size=5
                ),
            )

        self.assertEqual(
            context.exception.code,
            "file_size_exceeded",
        )

        with self.assertRaises(
            FolderUploadValidationError
        ) as context:
            build_folder_upload_plan(
                [
                    self.upload(
                        "Proyecto/a.bin",
                        b"123456",
                    ),
                    self.upload(
                        "Proyecto/b.bin",
                        b"123456",
                    ),
                ],
                destination_path=self.destination,
                limits=FolderUploadLimits(
                    max_total_size=10
                ),
            )

        self.assertEqual(
            context.exception.code,
            "total_size_exceeded",
        )

    def test_admite_manifiesto_de_carpeta_vacia(self):
        plan = build_folder_upload_plan(
            [],
            destination_path=self.destination,
            declared_directories=[
                "Proyecto",
                "Proyecto/vacia",
            ],
        )

        self.assertEqual(plan.root_name, "Proyecto")
        self.assertEqual(plan.files_count, 0)
        self.assertEqual(
            plan.directories,
            (
                "EMPRESA/DESTINO/Proyecto",
                "EMPRESA/DESTINO/Proyecto/vacia",
            ),
        )

    def test_crea_estructura_y_sube_archivos(self):
        gateway = FakeCloudGateway()

        plan = build_folder_upload_plan(
            [
                self.upload(
                    "Proyecto/documentos/informe.pdf"
                ),
                self.upload(
                    "Proyecto/imagenes/foto.jpg"
                ),
            ],
            destination_path=self.destination,
            gateway=gateway,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            policy=POLICY_SKIP,
        )

        self.assertEqual(result.uploaded_files, 2)
        self.assertEqual(result.error_files, 0)

        self.assertIn(
            "EMPRESA/DESTINO/Proyecto/documentos/informe.pdf",
            gateway.uploaded,
        )
        self.assertIn(
            "EMPRESA/DESTINO/Proyecto/imagenes/foto.jpg",
            gateway.uploaded,
        )

    def test_reutiliza_carpetas_existentes(self):
        gateway = FakeCloudGateway()

        gateway.items.update({
            "EMPRESA/DESTINO/Proyecto": "directory",
            "EMPRESA/DESTINO/Proyecto/documentos": (
                "directory"
            ),
        })

        plan = build_folder_upload_plan(
            [
                self.upload(
                    "Proyecto/documentos/informe.pdf"
                )
            ],
            destination_path=self.destination,
            gateway=gateway,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
        )

        self.assertEqual(result.uploaded_files, 1)
        self.assertEqual(result.created_folders, [])
        self.assertEqual(
            result.reused_folders,
            [
                "EMPRESA/DESTINO/Proyecto",
                "EMPRESA/DESTINO/Proyecto/documentos",
            ],
        )

    def test_omitir_existentes_no_detiene_lote(self):
        gateway = FakeCloudGateway()

        gateway.items.update({
            "EMPRESA/DESTINO/Proyecto": "directory",
            "EMPRESA/DESTINO/Proyecto/existe.txt": "file",
        })

        plan = build_folder_upload_plan(
            [
                self.upload("Proyecto/existe.txt"),
                self.upload("Proyecto/nuevo.txt"),
            ],
            destination_path=self.destination,
            gateway=gateway,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            policy=POLICY_SKIP,
        )

        self.assertEqual(result.skipped_files, 1)
        self.assertEqual(result.uploaded_files, 1)
        self.assertEqual(result.error_files, 0)

    def test_renombrado_automatico(self):
        gateway = FakeCloudGateway()

        gateway.items.update({
            "EMPRESA/DESTINO/Proyecto": "directory",
            "EMPRESA/DESTINO/Proyecto/informe.pdf": "file",
            "EMPRESA/DESTINO/Proyecto/informe (1).pdf": (
                "file"
            ),
        })

        plan = build_folder_upload_plan(
            [self.upload("Proyecto/informe.pdf")],
            destination_path=self.destination,
            gateway=gateway,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            policy=POLICY_RENAME,
        )

        self.assertEqual(result.uploaded_files, 1)
        self.assertEqual(
            result.file_results[0].status,
            "renamed",
        )
        self.assertEqual(
            result.file_results[0].target_path,
            "EMPRESA/DESTINO/Proyecto/informe (2).pdf",
        )

    def test_cancelar_no_realiza_modificaciones(self):
        gateway = FakeCloudGateway()

        gateway.items.update({
            "EMPRESA/DESTINO/Proyecto": "directory",
            "EMPRESA/DESTINO/Proyecto/existe.txt": "file",
        })

        plan = build_folder_upload_plan(
            [
                self.upload("Proyecto/existe.txt"),
                self.upload("Proyecto/nuevo.txt"),
            ],
            destination_path=self.destination,
            gateway=gateway,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            policy=POLICY_CANCEL,
        )

        self.assertTrue(result.cancelled)
        self.assertEqual(gateway.created, [])
        self.assertEqual(gateway.uploaded, [])
        self.assertEqual(gateway.deleted, [])

    def test_error_de_un_archivo_no_cancela_resto(self):
        gateway = FakeCloudGateway()
        gateway.fail_upload_names.add("fallo.txt")

        plan = build_folder_upload_plan(
            [
                self.upload("Proyecto/fallo.txt"),
                self.upload("Proyecto/correcto.txt"),
            ],
            destination_path=self.destination,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
        )

        self.assertEqual(result.error_files, 1)
        self.assertEqual(result.uploaded_files, 1)
        self.assertIn(
            "EMPRESA/DESTINO/Proyecto/correcto.txt",
            gateway.uploaded,
        )

    def test_reemplazar_exige_autorizacion_explicita(self):
        gateway = FakeCloudGateway()

        plan = build_folder_upload_plan(
            [self.upload("Proyecto/informe.pdf")],
            destination_path=self.destination,
        )

        with self.assertRaises(
            FolderUploadValidationError
        ) as context:
            execute_folder_upload(
                plan,
                gateway=gateway,
                policy=POLICY_REPLACE,
            )

        self.assertEqual(
            context.exception.code,
            "replace_not_authorized",
        )

    def test_reemplazo_controlado_usa_temporal(self):
        gateway = FakeCloudGateway()

        gateway.items.update({
            "EMPRESA/DESTINO/Proyecto": "directory",
            "EMPRESA/DESTINO/Proyecto/informe.pdf": "file",
        })

        plan = build_folder_upload_plan(
            [self.upload("Proyecto/informe.pdf", b"nuevo")],
            destination_path=self.destination,
            gateway=gateway,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            policy=POLICY_REPLACE,
            allow_replace=True,
        )

        self.assertEqual(result.uploaded_files, 1)
        self.assertEqual(
            result.file_results[0].status,
            "replaced",
        )
        self.assertIn(
            "EMPRESA/DESTINO/Proyecto/informe.pdf",
            gateway.items,
        )
        self.assertEqual(
            gateway.items[
                "EMPRESA/DESTINO/Proyecto/informe.pdf"
            ],
            "file",
        )
        self.assertIn(
            "EMPRESA/DESTINO/Proyecto/informe.pdf",
            gateway.deleted,
        )
        self.assertEqual(len(gateway.moved), 1)

    def test_callback_referencia_y_progreso(self):
        gateway = FakeCloudGateway()
        references = []
        progress = []

        plan = build_folder_upload_plan(
            [self.upload("Proyecto/informe.pdf")],
            destination_path=self.destination,
        )

        result = execute_folder_upload(
            plan,
            gateway=gateway,
            reference_writer=lambda planned, item, target: (
                references.append((
                    planned.relative_path,
                    item["storage_key"],
                    target,
                ))
            ),
            progress_callback=progress.append,
        )

        self.assertEqual(result.uploaded_files, 1)
        self.assertEqual(len(references), 1)
        self.assertEqual(progress[-1]["percent"], 100.0)
        self.assertEqual(progress[-1]["pending"], 0)
