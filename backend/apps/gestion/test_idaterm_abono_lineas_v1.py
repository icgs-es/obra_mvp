import inspect

from decimal import Decimal

from django.test import SimpleTestCase

from apps.gestion import views

from apps.gestion.services.facturas_pdf import (
    _portal_idaterm_factura_abono_extract_lines_v1,
)


class IdatermAbonoLineasV1Tests(
    SimpleTestCase,
):

    TEXT = """
    IDATERM, S.L.

    ABONO AB26/01371

    Nº recep. devol. ALAB26/02337:
    Nº envío AV26/13454:

    P01382800
    PLACA STD BA 13x1200x2800mm. -PLACO
    Cód. productor-producto: ENV/2023/000002888
    136 Placas 456,96 M2 15,01€/PLACA 43% 1.163,58€

    Hay 3,36 M2 por PLACA.

    Nº envío AV26/24950:

    P01503000PH
    PLACA PHONIQUE 15x1200x3000mm. -PLACO
    Cód. productor-producto: ENV/2023/000002888
    20 Placas 72 M2 34,99€/PLACA 40% 419,88€

    CORRESPONDE A LA FACTURA
    - FV26/07450

    BASE IMPONIBLE 1.583,46€
    IVA 332,53€
    TOTAL 1.915,99€
    """


    def test_detecta_dos_lineas(
        self,
    ):
        parsed = (
            _portal_idaterm_factura_abono_extract_lines_v1(
                self.TEXT
            )
        )

        self.assertEqual(
            len(parsed["lineas"]),
            2,
        )

        self.assertEqual(
            parsed["parser"],
            "idaterm_factura_abono_v1",
        )

        self.assertEqual(
            parsed["total_lineas"],
            "-1583.46",
        )


    def test_linea_uno(
        self,
    ):
        line = (
            _portal_idaterm_factura_abono_extract_lines_v1(
                self.TEXT
            )["lineas"][0]
        )

        self.assertEqual(
            line["codigo"],
            "P01382800",
        )

        self.assertEqual(
            line["cantidad"],
            "136.0000",
        )

        self.assertEqual(
            line["precio"],
            "15.0100",
        )

        self.assertEqual(
            line["descuento"],
            "43.00",
        )

        self.assertEqual(
            line["importe_documental"],
            "1163.58",
        )

        self.assertEqual(
            line["importe"],
            "-1163.58",
        )

        self.assertEqual(
            line["numero_envio"],
            "AV26/13454",
        )

        self.assertEqual(
            line[
                "numero_recepcion_devolucion"
            ],
            "ALAB26/02337",
        )

        self.assertEqual(
            line[
                "num_albaran_proveedor"
            ],
            "",
        )


    def test_linea_dos(
        self,
    ):
        line = (
            _portal_idaterm_factura_abono_extract_lines_v1(
                self.TEXT
            )["lineas"][1]
        )

        self.assertEqual(
            line["codigo"],
            "P01503000PH",
        )

        self.assertEqual(
            line["cantidad"],
            "20.0000",
        )

        self.assertEqual(
            line["precio"],
            "34.9900",
        )

        self.assertEqual(
            line["descuento"],
            "40.00",
        )

        self.assertEqual(
            line["importe"],
            "-419.88",
        )

        self.assertEqual(
            line["numero_envio"],
            "AV26/24950",
        )


    def test_formula_documental_cuadra(
        self,
    ):
        parsed = (
            _portal_idaterm_factura_abono_extract_lines_v1(
                self.TEXT
            )
        )

        expected = (
            Decimal("136")
            * Decimal("15.01")
            * Decimal("0.57")
        ).quantize(
            Decimal("0.01")
        )

        self.assertEqual(
            expected,
            Decimal("1163.58"),
        )

        self.assertEqual(
            abs(
                Decimal(
                    parsed["lineas"][0][
                        "importe"
                    ]
                )
            ),
            expected,
        )


    def test_vista_rutea_por_parser_key(
        self,
    ):
        """
        Contrato canónico de routing.

        La vista no debe conocer implementaciones específicas.

        vista
          -> extract_factura_lines_by_template_v1
          -> parser específico IDATERM/JOMA/etc.
        """

        import inspect

        from apps.gestion import views

        from apps.gestion.services.facturas_pdf import (
            extract_factura_lines_by_template_v1,
        )


        view_source = inspect.getsource(
            views.factura_lineas_desde_ocr
        )


        self.assertIn(
            "FACTURA_LINEAS_TEMPLATE_ROUTING_V1",
            view_source,
        )

        self.assertIn(
            "extract_factura_lines_by_template_v1",
            view_source,
        )


        dispatcher_source = inspect.getsource(
            extract_factura_lines_by_template_v1
        )


        self.assertIn(
            "idaterm_factura_valorada_v1",
            dispatcher_source,
        )

        self.assertIn(
            "_portal_idaterm_factura_abono_extract_lines_v1",
            dispatcher_source,
        )

        self.assertIn(
            '"ABONO"',
            dispatcher_source,
        )



    def test_vista_preserva_cabecera_abono(
        self,
    ):
        source = inspect.getsource(
            views.factura_lineas_desde_ocr
        )

        self.assertIn(
            "FACTURA_ABONO_OCR_HEADER_PRESERVE_V2",
            source,
        )

        self.assertIn(
            "_factura_header_before_lineas_ocr_v2",
            source,
        )
