"""Casos de prueba del E3 §6.9 (ISO/IEC/IEEE 29119) que se pueden automatizar.

  python manage.py test registro -v 2
"""
import io
import json
import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from . import firma, servicios, validacion
from .context import GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS
from .models import Alumno, Aviso, Bitacora, Configuracion, Conferencia, Lote, Pregunta, Registro

# Las pruebas del E4 usan los dos canales y sin aviso de «recibido»; las del salón (al final) los cambian.
PRUEBAS = dict(NOTIF_ASYNC=False, NOTIF_MODO="real", WHATSAPP_ENABLED=True,
               NOTIF_CANALES=["correo", "whatsapp"], NOTIF_AVISO_RECIBIDO=False, WHATSAPP_PAUSA_SEG=0, LIMITES_ACTIVOS=False,
               EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


@override_settings(**PRUEBAS)
class Base(TestCase):
    def setUp(self):
        self.cfg = Configuracion.actual()
        self.g = {n: Group.objects.create(name=n) for n in (GRUPO_COMITE, GRUPO_PROFESOR, GRUPO_SERVICIOS)}
        self.comite = self._user("comite", GRUPO_COMITE)
        self.profe = self._user("profesor", GRUPO_PROFESOR)
        self.se = self._user("servicios", GRUPO_SERVICIOS)
        for i, carrera in enumerate(["SIS", "CIV", "IND", "SIS"], 1):
            Alumno.objects.create(no_control=f"9966000{i}", nombre="María", apellidos=f"Sánchez {i}",
                                  carrera=carrera, semestre=3, grupo="A", telefono=f"488000000{i}",
                                  correo=f"l9966000{i}@ejemplo.test")
        for a in Alumno.objects.all():   # NIP de prueba: 1234 para todos
            a.set_nip("1234")
            a.save()
        ahora = timezone.localtime()
        ini = (ahora - timedelta(minutes=30)).replace(second=0, microsecond=0)
        self.conf = self._conf("Conferencia activa", ini, ini + timedelta(minutes=90))
        self.m = firma.minuto_actual()
        # requests.post del servicio de WhatsApp simulado (no se envía nada real en pruebas)
        p = mock.patch("registro.notificaciones.requests.post",
                       return_value=mock.Mock(status_code=200, text="ok"))
        self.wa = p.start()
        self.addCleanup(p.stop)

    def _user(self, nombre, grupo):
        u = User.objects.create_user(nombre, password="x12345678")
        u.groups.add(self.g[grupo])
        return u

    def _conf(self, nombre, ini, fin):
        c = Conferencia.objects.create(nombre=nombre, fecha=ini.date(), hora_inicio=ini.time(), hora_fin=fin.time(),
                                       creditos=1, profesor=self.profe)
        for n in range(5):
            Pregunta.objects.create(conferencia=c, orden=n, texto=f"P{n}", opciones=["a", "b", "c"], correcta=0)
        return c

    def registrar(self, nc="99660001", resp=None, t=150, minuto=None, conf=None, u=None, nip="1234", laptop=False):
        """laptop=True: como si lo subiera la laptop del profesor (modo B), que ya verificó NIP y hora de llegada."""
        conf = conf or self.conf
        return servicios.registrar_por_qr(
            uuid=u or uuid.uuid4(), token=firma.firmar(conf, minuto or self.m), no_control=nc, nip=nip,
            respuestas=resp if resp is not None else [0, 0, 0, 0, 0], tiempo_seg=t, nip_verificado=laptop)


class TC01_Conferencia(Base):
    """TC-01 · FR-01, RN-03 · valores límite de créditos."""

    def test_creditos_limite(self):
        c = Client()
        c.force_login(self.comite)
        datos = dict(nombre="Nueva", lugar="Sala", fecha=timezone.localdate().isoformat(), hora_inicio="10:00",
                     hora_fin="11:00", profesor=self.profe.pk, carreras_sel=["SIS"],
                     preguntas="¿Uno? | *Sí | No")
        r2 = c.post("/comite/", dict(datos, creditos=2))
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(Conferencia.objects.filter(nombre="Nueva", creditos=2).exists())
        r3 = c.post("/comite/", dict(datos, nombre="Tres", creditos=3))
        self.assertEqual(r3.status_code, 200)
        self.assertFalse(Conferencia.objects.filter(nombre="Tres").exists())

    def test_sin_cuestionario_se_rechaza(self):
        c = Client()
        c.force_login(self.comite)
        r = c.post("/comite/", dict(nombre="X", lugar="S", fecha="2026-11-17", hora_inicio="10:00", hora_fin="11:00",
                                    creditos=1, profesor=self.profe.pk, carreras_sel=["SIS"], preguntas=""))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Conferencia.objects.filter(nombre="X").exists())


class TC02_QR(Base):
    """TC-02 · FR-02, RN-11 · partición de equivalencia del QR."""

    def test_paquete_un_qr_distinto_por_minuto(self):
        paquete = firma.paquete_qr(self.conf)
        self.assertEqual(len(paquete), 90 + self.cfg.tolerancia_min + 1)
        self.assertEqual(len({t for _, t in paquete}), len(paquete))

    def test_ventana(self):
        fin_ventana = firma.minuto_de(self.conf.cierre_dt())
        r_ok, *_ = self.registrar("99660001", minuto=self.m)
        r_fuera, *_ = self.registrar("99660002", minuto=fin_ventana + 1)  # 16 min después del fin
        r_antes, *_ = self.registrar("99660003", minuto=firma.minuto_de(self.conf.inicio_dt()) - 2)
        self.assertTrue(r_ok.valido)
        self.assertEqual(r_fuera.motivo, validacion.MOTIVO_VENTANA)
        self.assertEqual(r_antes.motivo, validacion.MOTIVO_VENTANA)

    def test_qr_alterado_rechazado(self):
        token = firma.firmar(self.conf, self.m)
        alterado = token[:-1] + ("0" if token[-1] != "0" else "1")
        with self.assertRaises(servicios.ErrorRegistro):
            servicios.registrar_por_qr(uuid=uuid.uuid4(), token=alterado, no_control="99660001",
                                       respuestas=[0] * 5, tiempo_seg=150)
        otro_minuto = f"{self.conf.pk}.{self.m + 1}.{token.split('.')[2]}"
        with self.assertRaises(servicios.ErrorRegistro):
            servicios.registrar_por_qr(uuid=uuid.uuid4(), token=otro_minuto, no_control="99660001",
                                       respuestas=[0] * 5, tiempo_seg=150)


class TC03_Padron(Base):
    """TC-03 · FR-03 · 3 filas válidas, 1 sin número de control, 1 con carrera vacía."""

    def test_carga(self):
        csv = ("no_control,nip,nombre,apellidos,carrera,semestre,grupo,telefono,correo\n"
               "11110001,0412,Ana,Pérez,SIS,1,A,4880000001,a@ejemplo.test\n"
               "11110002,7730,Luis,Ruiz,Ing. Civil,3,B,,l@ejemplo.test\n"
               "11110003,9005,Eva,Gil,IND,5,A,4880000003,e@ejemplo.test\n"
               ",1111,Sin,Numero,SIS,1,A,,s@ejemplo.test\n"
               "11110005,2222,Sin,Carrera,,1,A,,c@ejemplo.test\n"
               "11110006,12,Nip,Corto,SIS,1,A,,n@ejemplo.test\n")
        r = servicios.cargar_padron(csv, self.se)
        self.assertEqual(r["aceptadas"], 3)
        self.assertEqual([f for f, _ in r["rechazadas"]], [5, 6, 7])
        self.assertIn("número de control", r["rechazadas"][0][1])
        self.assertIn("carrera", r["rechazadas"][1][1])
        self.assertIn("NIP", r["rechazadas"][2][1])
        ana = Alumno.objects.get(pk="11110001")
        self.assertTrue(ana.nip_coincide("0412"))
        self.assertNotIn("0412", ana.nip_hash)   # el NIP no se guarda en claro

    def test_columna_faltante(self):
        with self.assertRaisesMessage(servicios.ErrorRegistro, "faltan las columnas: correo"):
            servicios.cargar_padron("no_control,nip,nombre,apellidos,carrera,semestre,grupo,telefono\n", self.se)


class TC04_Identificacion(Base):
    """TC-04 · FR-04, FR-28, RN-09."""

    def test_api_identificar(self):
        c = Client()
        r = c.post("/api/identificar", json.dumps({"no_control": "99660001", "nip": "1234",
                   "conferencia": self.conf.pk}), content_type="application/json")
        self.assertEqual(r.json()["nombre_parcial"], "M* S*")
        r = c.post("/api/identificar", json.dumps({"no_control": "12345678", "nip": "1234"}),
                   content_type="application/json")
        self.assertEqual(r.status_code, 404)
        self.assertIn("Revisa", r.json()["error"])
        reg, *_ = self.registrar("99660001")
        r = c.post("/api/identificar", json.dumps({"no_control": "99660001", "nip": "1234",
                   "conferencia": self.conf.pk}), content_type="application/json")
        self.assertTrue(r.json()["ya_registrado"])
        self.assertEqual(r.json()["registro"]["folio"], reg.folio)

    def _identificar(self, nc, nip):
        return Client().post("/api/identificar", json.dumps({"no_control": nc, "nip": nip, "conferencia": self.conf.pk}),
                             content_type="application/json")

    def test_nip_incorrecto_no_muestra_datos(self):
        """Con el número de control de un compañero pero sin su NIP no se puede continuar ni ver su nombre."""
        for nip in ("0000", "", "12345", "abcd"):
            r = self._identificar("99660002", nip)
            self.assertEqual(r.status_code, 403)
            self.assertNotIn("nombre_parcial", r.json())
            self.assertIn("NIP", r.json()["error"])

    def test_nip_incorrecto_no_registra(self):
        """También al sincronizar un registro hecho sin internet: el NIP se verifica en el servidor."""
        r = Client().post("/api/registros", json.dumps({
            "uuid": str(uuid.uuid4()), "token": firma.firmar(self.conf, self.m), "no_control": "99660002",
            "nip": "9999", "respuestas": [0] * 5, "tiempo_seg": 120}), content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Registro.objects.count(), 0)
        with self.assertRaises(servicios.ErrorRegistro):
            self.registrar("99660002", nip=None)
        self.assertEqual(Registro.objects.count(), 0)

    def test_bloqueo_tras_cinco_intentos(self):
        for _ in range(5):
            self.assertEqual(self._identificar("99660003", "0000").status_code, 403)
        r = self._identificar("99660003", "1234")           # ya ni con el NIP correcto
        self.assertEqual(r.status_code, 429)
        self.assertIn("15 minutos", r.json()["error"])
        Alumno.objects.filter(pk="99660003").update(nip_bloqueado_hasta=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._identificar("99660003", "1234").status_code, 200)
        self.assertEqual(self._identificar("99660004", "1234").status_code, 200)   # no afecta a otros alumnos

    def test_laptop_del_profesor_sincroniza_con_firma(self):
        """Modo B: la laptop ya verificó el NIP y sube el registro firmado, sin reenviar el NIP."""
        u = uuid.uuid4()
        cuerpo = {"uuid": str(u), "token": firma.firmar(self.conf, self.m), "no_control": "99660004",
                  "respuestas": [0] * 5, "tiempo_seg": 120, "origen": "red_local"}
        r = Client().post("/api/registros", json.dumps({**cuerpo, "sync_firma": "falsa"}), content_type="application/json")
        self.assertEqual(r.status_code, 403)
        r = Client().post("/api/registros", json.dumps({**cuerpo, "sync_firma": firma.firma_sync(u)}),
                          content_type="application/json")
        self.assertEqual(r.status_code, 201)


class TC05_Cuestionario(Base):
    """TC-05 · FR-05, RN-09 · incompleto, completo y segundo intento."""

    def test_intentos(self):
        with self.assertRaises(servicios.ErrorRegistro):
            self.registrar(resp=[0, 0, None, 0, 0])
        r1, nuevo, dup = self.registrar()
        self.assertTrue(nuevo)
        self.assertEqual(r1.tiempo_seg, 150)
        r2, nuevo2, dup2 = self.registrar(resp=[1, 1, 1, 1, 1])
        self.assertFalse(nuevo2)
        self.assertTrue(dup2)
        self.assertEqual(r2.pk, r1.pk)
        self.assertEqual(Registro.objects.count(), 1)

    def test_paquete_trae_tiempo_minimo(self):
        """D-13 (pruebas con usuarios): la app debe conocer el tiempo mínimo para mostrar cuánto falta."""
        j = self.client.get(f"/api/paquete/{self.conf.pk}").json()
        self.assertEqual(j["tiempo_minimo_seg"], 100)   # 5 preguntas × 20 s (RN-15)
        self.assertEqual(j["tiempo_minimo_seg"], validacion.tiempo_minimo(5, self.cfg))


class TC08_Sincronizacion(Base):
    """TC-08 · FR-23, NFR-11 · 10 registros reenviados llegan una sola vez."""

    def test_idempotencia_api(self):
        c = Client()
        uuids = [str(uuid.uuid4()) for _ in range(4)]
        for _ in range(3):   # se reenvían tres veces, como haría un celular con mala señal
            for u, nc in zip(uuids, ["99660001", "99660002", "99660003", "99660004"]):
                r = c.post("/api/registros", json.dumps({"uuid": u, "token": firma.firmar(self.conf, self.m),
                           "no_control": nc, "nip": "1234", "respuestas": [0] * 5, "tiempo_seg": 120}),
                           content_type="application/json")
                self.assertIn(r.status_code, (200, 201))
        self.assertEqual(Registro.objects.count(), 4)


class TC09_Validacion(Base):
    """TC-09 · FR-25, RN-09, RN-11, RN-14, RN-15 · tabla de decisión y valores límite."""

    def test_tabla_de_decision(self):
        ev = validacion.evaluar
        dentro = self.conf.inicio_dt() + timedelta(minutes=5)
        fuera = self.conf.cierre_dt() + timedelta(minutes=1)
        self.assertEqual(ev(self.conf, dentro, 100, 3, 5, False), (True, ""))
        self.assertEqual(ev(self.conf, fuera, 100, 5, 5, False)[1], validacion.MOTIVO_VENTANA)
        self.assertEqual(ev(self.conf, dentro, 100, 5, 5, True)[1], validacion.MOTIVO_DUPLICADO)
        self.assertEqual(ev(self.conf, dentro, 99, 5, 5, False)[1], validacion.MOTIVO_RAPIDO)      # 19.8 s/preg
        self.assertEqual(ev(self.conf, dentro, 100, 5, 5, False), (True, ""))                    # 20 s/preg
        self.assertEqual(ev(self.conf, dentro, 300, 49, 100, False)[1], validacion.MOTIVO_PUNTAJE)  # 49 %
        self.assertEqual(ev(self.conf, dentro, 2000, 50, 100, False), (True, ""))                 # 50 %

    def test_tope_de_tiempo_minimo(self):
        self.assertEqual(validacion.tiempo_minimo(30, self.cfg), 300)   # nunca más de 5 min

    def test_registro_no_valido_avisa(self):
        r, *_ = self.registrar(resp=[1, 1, 1, 0, 0])   # 40 %
        self.assertFalse(r.valido)
        self.assertEqual(r.motivo, validacion.MOTIVO_PUNTAJE)
        self.assertEqual(len(mail.outbox), 1)        # FR-15
        self.assertIn("no fue válido", mail.outbox[0].subject)


class TC10_Credito(Base):
    """TC-10 · FR-26, RN-13, FR-16 · 1 conferencia sin crédito, 2 con crédito; nunca se muestra el mínimo."""

    def test_credito(self):
        ayer = timezone.localtime() - timedelta(days=1)
        otra = self._conf("Ayer", ayer.replace(hour=10, minute=0), ayer.replace(hour=11, minute=0))
        self.registrar("99660001")
        self.registrar("99660002")
        self.registrar("99660001", conf=otra, minuto=firma.minuto_de(otra.inicio_dt()) + 5, laptop=True)  # llegó ayer
        lote = servicios.enviar_validos(self.comite)
        filas = {f["no_control"]: f for f in servicios.filas_csv(lote)}
        self.assertEqual(filas["99660002"]["credito"], "NO")
        self.assertEqual(filas["99660001"]["credito"], "SI")
        self.assertEqual(filas["99660001"]["conferencias_validas"], 2)

    def test_estado_no_muestra_minimo(self):
        self.registrar("99660001")
        c = Client()
        c.post("/api/estado/codigo", json.dumps({"no_control": "99660001"}), content_type="application/json")
        codigo = mail.outbox[-1].body.split("es:")[1].split()[0]
        r = c.post("/api/estado", json.dumps({"no_control": "99660001", "codigo": codigo}),
                   content_type="application/json")
        self.assertTrue(r.json()["ok"])
        texto = r.content.decode().lower()
        self.assertNotIn("mínimo", texto)
        self.assertNotIn("necesitas", texto)
        r2 = c.post("/api/estado", json.dumps({"no_control": "99660001", "codigo": codigo}),
                    content_type="application/json")
        self.assertEqual(r2.status_code, 403)   # el código es de un solo uso


class TC11_Tablero(Base):
    """TC-11 · FR-08, FR-09 · la suma por estado coincide con el total."""

    def test_suma(self):
        self.registrar("99660001")
        self.registrar("99660002", t=10)
        self.registrar("99660003", resp=[1] * 5)
        c = Client()
        c.force_login(self.comite)
        r = c.get("/comite/tablero/")
        for f in r.context["filas"]:
            self.assertEqual(f["total"], f["validos_pend"] + f["enviados"] + f["no_validos"])
        self.assertEqual(r.context["tot"]["total"], 3)
        d = c.get("/comite/tablero/CIV/")
        self.assertContains(d, validacion.MOTIVO_RAPIDO)


class TC12_Enviar(Base):
    """TC-12 · FR-10, RN-10 · solo válidos, una sola vez, en bitácora."""

    def test_enviar_una_vez(self):
        self.registrar("99660001")
        self.registrar("99660002", resp=[1] * 5)
        lote = servicios.enviar_validos(self.comite)
        self.assertEqual(lote.registros.count(), 1)
        self.assertIsNone(servicios.enviar_validos(self.comite))
        self.assertEqual(Lote.objects.count(), 1)
        self.assertTrue(Bitacora.objects.filter(accion="Envío a Servicios Escolares").exists())


class TC13_CSV(Base):
    """TC-13 · FR-11, NFR-09."""

    def test_csv(self):
        self.registrar("99660001")
        self.registrar("99660002")
        lote = servicios.enviar_validos(self.comite)
        contenido, problemas = servicios.generar_csv(lote, self.se)
        self.assertEqual(problemas, [])
        lineas = contenido.lstrip("﻿").strip().splitlines()
        self.assertEqual(lineas[0].split(","), servicios.COLUMNAS_CSV)
        self.assertEqual(len(lineas), 3)
        contenido.encode("utf-8")

    def test_columna_vacia_bloquea(self):
        self.registrar("99660001")
        lote = servicios.enviar_validos(self.comite)
        Alumno.objects.filter(pk="99660001").update(grupo="")
        contenido, problemas = servicios.generar_csv(lote, self.se)
        self.assertIsNone(contenido)
        self.assertEqual(problemas, [(2, ["grupo"])])


class TC14_Avisos(Base):
    """TC-14 · FR-12, FR-13, FR-14, FR-27, RN-16."""

    def test_confirmar_avisa_por_correo_y_whatsapp(self):
        self.registrar("99660001")
        lote = servicios.enviar_validos(self.comite)
        servicios.confirmar_carga(lote, self.se)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.wa.call_count, 1)
        self.assertEqual(Aviso.objects.filter(estado=Aviso.ENVIADO).count(), 2)
        with self.assertRaises(servicios.ErrorRegistro):   # no se repiten avisos
            servicios.confirmar_carga(lote, self.se)

    def test_falla_exige_motivo_y_avisa(self):
        self.registrar("99660001")
        lote = servicios.enviar_validos(self.comite)
        with self.assertRaises(servicios.ErrorRegistro):
            servicios.reportar_falla(lote, self.se, "  ")
        servicios.reportar_falla(lote, self.se, "Formato de fecha")
        self.assertIn("Formato de fecha", mail.outbox[0].body)
        self.assertIn(self.cfg.contacto_encargado, mail.outbox[0].body)

    def test_whatsapp_falla_queda_registrado_y_correo_sale(self):
        self.wa.return_value = mock.Mock(status_code=503, text="sin sesión")
        self.registrar("99660001")
        servicios.confirmar_carga(servicios.enviar_validos(self.comite), self.se)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Aviso.objects.filter(canal=Aviso.WHATSAPP, estado=Aviso.ERROR).exists())

    @override_settings(NOTIF_MODO="prueba", NOTIF_LISTA_BLANCA_CORREOS=[], NOTIF_LISTA_BLANCA_TELEFONOS=[])
    def test_modo_prueba_no_envia_fuera_de_lista(self):
        self.registrar("99660001")
        servicios.confirmar_carga(servicios.enviar_validos(self.comite), self.se)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.wa.call_count, 0)
        self.assertEqual(Aviso.objects.filter(estado=Aviso.SIMULADO).count(), 2)


class TC15_Roles(Base):
    """TC-15 · NFR-07 · 0 accesos indebidos."""

    def test_roles(self):
        rutas = {GRUPO_COMITE: "/comite/", GRUPO_PROFESOR: "/profesor/", GRUPO_SERVICIOS: "/servicios/"}
        usuarios = {GRUPO_COMITE: self.comite, GRUPO_PROFESOR: self.profe, GRUPO_SERVICIOS: self.se}
        for rol, u in usuarios.items():
            c = Client()
            c.force_login(u)
            for rol_ruta, ruta in rutas.items():
                esperado = 200 if rol == rol_ruta else 403
                self.assertEqual(c.get(ruta).status_code, esperado, f"{u.username} → {ruta}")
        self.assertEqual(Client().get("/comite/").status_code, 302)  # sin sesión, al login


class TC07_Asistido(Base):
    """FR-07 · el registro asistido exige motivo y queda marcado."""

    def test_asistido(self):
        with self.assertRaises(servicios.ErrorRegistro):
            servicios.registrar_asistido(conferencia=self.conf, no_control="99660001", motivo="", usuario=self.profe)
        r = servicios.registrar_asistido(conferencia=self.conf, no_control="99660001", motivo="Sin batería",
                                         usuario=self.profe)
        self.assertTrue(r.valido)
        self.assertEqual(r.origen, Registro.ASISTIDO)


SALON = dict(NOTIF_CANALES=["whatsapp"], NOTIF_AVISO_RECIBIDO=True, NOTIF_MODO="prueba",
             NOTIF_LISTA_BLANCA_TELEFONOS=[], NOTIF_TELEFONO_ALUMNO=True)


@override_settings(**SALON)
class TS01_VersionSalon(Base):
    """Versión del salón (24 nov 2026): el alumno escribe su WhatsApp y recibe el aviso solo por ahí."""

    def setUp(self):
        super().setUp()
        Alumno.objects.update(telefono="", telefono_del_alumno=False)

    def test_telefono_escrito_recibe_confirmacion_por_whatsapp(self):
        servicios.registrar_por_qr(uuid=uuid.uuid4(), token=firma.firmar(self.conf, self.m), no_control="99660001",
                                   nip="1234", respuestas=[0] * 5, tiempo_seg=150, telefono="+52 1 488 123 4567")
        a = Alumno.objects.get(pk="99660001")
        self.assertEqual((a.telefono, a.telefono_del_alumno), ("4881234567", True))
        self.assertEqual(self.wa.call_count, 1)                      # fuera de la lista blanca, pero lo escribió él
        self.assertEqual(self.wa.call_args.kwargs["json"]["telefono"], "4881234567")
        self.assertIn("Instituto Tecnológico de Matehuala", self.wa.call_args.kwargs["json"]["mensaje"])
        self.assertEqual(len(mail.outbox), 0)                        # sin correo

    def test_nip_equivocado_no_guarda_telefono(self):
        with self.assertRaises(servicios.ErrorRegistro):
            servicios.registrar_por_qr(uuid=uuid.uuid4(), token=firma.firmar(self.conf, self.m),
                                       no_control="99660001", nip="9999", respuestas=[0] * 5, tiempo_seg=150,
                                       telefono="4881234567")
        self.assertEqual(Alumno.objects.get(pk="99660001").telefono, "")
        self.assertEqual(self.wa.call_count, 0)

    def test_telefono_del_padron_sigue_en_lista_blanca(self):
        Alumno.objects.filter(pk="99660002").update(telefono="4880000002")   # no lo escribió el alumno
        self.registrar("99660002")
        self.assertEqual(self.wa.call_count, 0)
        self.assertTrue(Aviso.objects.filter(estado=Aviso.SIMULADO).exists())

    def test_api_codigo_por_whatsapp(self):
        c = Client()
        r = c.post("/api/registros", json.dumps({
            "uuid": str(uuid.uuid4()), "token": firma.firmar(self.conf, self.m), "no_control": "99660001",
            "nip": "1234", "respuestas": [0] * 5, "tiempo_seg": 150, "telefono": "4881234567"}),
            content_type="application/json")
        self.assertEqual(r.status_code, 201)
        r = c.post("/api/estado/codigo", json.dumps({"no_control": "99660001"}), content_type="application/json")
        self.assertIn("WhatsApp 488 *** **67", r.json()["destino"])
        self.assertEqual(self.wa.call_count, 2)   # confirmación + código

    def test_preparar_salon(self):
        from django.core.management import call_command
        from io import StringIO
        call_command("preparar_salon", "--sin-datos", stdout=StringIO())
        c = Conferencia.objects.get(nombre__startswith="Renueva TI")
        self.assertEqual(c.preguntas.count(), 6)
        self.assertEqual(f"{c.hora_fin:%H:%M}", "23:59")


@override_settings(LIMITES_ACTIVOS=True, LOGIN_MAX_INTENTOS=3)
class TS02_Limites(Base):
    """Seguridad (versión del salón): límites de intentos por dispositivo."""

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

    def test_login_se_bloquea(self):
        c = Client()
        for _ in range(3):
            c.post("/login/", {"username": "comite", "password": "mala"})
        r = c.post("/login/", {"username": "comite", "password": "x12345678"})   # aun con la buena
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Demasiados intentos")

    def test_codigo_limitado(self):
        c = Client()
        codigos = [c.post("/api/estado/codigo", json.dumps({"no_control": "00000000"}),
                          content_type="application/json").status_code for _ in range(6)]
        self.assertEqual(codigos[-1], 429)



class TS03_Integridad(Base):
    """Seguridad (versión del salón): sellos de registros y bitácora encadenada."""

    def test_registro_sellado_y_alteracion_detectada(self):
        from .integridad import verificar
        r, _, _ = self.registrar("99660001", resp=[1, 1, 1, 1, 1])   # < 50 %: no válido
        self.assertFalse(r.valido)
        self.assertTrue(verificar()["ok"])
        Registro.objects.filter(pk=r.pk).update(valido=True, motivo="")   # «hackeo» directo a la base
        v = verificar()
        self.assertFalse(v["ok"])
        self.assertIn(r.folio, v["problemas"][0])

    def test_lote_no_rompe_el_sello(self):
        from .integridad import verificar
        self.registrar("99660001")
        servicios.enviar_validos(self.comite)
        self.assertTrue(verificar()["ok"])

    def test_bitacora_encadenada(self):
        from .integridad import verificar
        for i in range(4):
            Bitacora.registrar(self.comite, f"Acción {i}", "obj")
        self.assertTrue(verificar()["ok"])
        Bitacora.objects.filter(accion="Acción 1").delete()             # borrar una entrada
        self.assertFalse(verificar()["ok"])

    def test_bitacora_editada(self):
        from .integridad import verificar
        Bitacora.registrar(self.comite, "Envío", "lote", "10 registros")
        Bitacora.objects.filter(accion="Envío").update(detalle="99 registros")
        self.assertFalse(verificar()["ok"])

    def test_consulta_queda_en_bitacora(self):
        from django.core.cache import cache
        cache.clear()
        c = Client()
        c.force_login(self.comite)
        c.get("/comite/tablero/")
        c.get("/comite/tablero/")   # recargar no duplica
        self.assertEqual(Bitacora.objects.filter(accion="Consulta: tablero por carrera").count(), 1)



class TS04_Correcciones(Base):
    """Correcciones de la auditoría del 25 nov 2026."""

    def test_registro_que_llega_tarde_no_es_valido(self):
        """Una foto del QR (o un registro sin internet) que llega después del cierre + margen ya no vale."""
        ayer = timezone.localtime() - timedelta(days=1)
        otra = self._conf("Ayer", ayer.replace(hour=10, minute=0), ayer.replace(hour=11, minute=0))
        minuto = firma.minuto_de(otra.inicio_dt()) + 5   # QR auténtico, tomado dentro del horario
        r, *_ = self.registrar("99660001", conf=otra, minuto=minuto)
        self.assertFalse(r.valido)
        self.assertEqual(r.motivo, validacion.MOTIVO_TARDE)
        r2, *_ = self.registrar("99660002", conf=otra, minuto=minuto, laptop=True)   # la laptop lo recibió a tiempo
        self.assertTrue(r2.valido)
        # Dentro del margen sí vale: cierre (fin + tolerancia) + margen de envío
        limite = validacion.limite_llegada(otra, self.cfg)
        self.assertEqual(validacion.evaluar(otra, otra.inicio_dt(), 150, 5, 5, False, llegada=limite), (True, ""))

    def test_profesor_no_toca_conferencias_de_otro(self):
        otro = self._user("profesor2", GRUPO_PROFESOR)
        c = Client()
        c.force_login(otro)
        pk = self.conf.pk
        self.assertEqual(c.get(f"/profesor/{pk}/").status_code, 404)
        self.assertEqual(c.get(f"/profesor/{pk}/estado").status_code, 404)
        self.assertEqual(c.post(f"/profesor/{pk}/asistido", {"no_control": "99660001", "motivo": "x"}).status_code, 404)
        self.assertEqual(c.post(f"/profesor/{pk}/sincronizar").status_code, 404)
        self.assertEqual(Registro.objects.count(), 0)
        c.force_login(self.profe)   # el dueño sí
        self.assertEqual(c.get(f"/profesor/{pk}/estado").status_code, 200)

    def test_intentos_de_nip_al_mismo_tiempo_cuentan_todos(self):
        """Dos peticiones que leyeron el mismo alumno (contador en 0) deben sumar 2, no 1."""
        a1, a2 = Alumno.objects.get(pk="99660001"), Alumno.objects.get(pk="99660001")
        for a in (a1, a2):
            with self.assertRaises(servicios.ErrorRegistro):
                servicios.verificar_nip(a, "0000")
        self.assertEqual(Alumno.objects.get(pk="99660001").nip_intentos, 2)

    def test_reintentar_no_repite_pendientes_recientes(self):
        from .notificaciones import reintentar_errores
        a = Alumno.objects.get(pk="99660001")
        nuevo = dict(alumno=a, canal=Aviso.WHATSAPP, tipo="t", destino=a.telefono, asunto="a", contenido="c")
        Aviso.objects.create(estado=Aviso.PENDIENTE, **nuevo)                 # sigue en la fila: no se toca
        viejo = Aviso.objects.create(estado=Aviso.PENDIENTE, **nuevo)
        Aviso.objects.filter(pk=viejo.pk).update(creado=timezone.now() - timedelta(minutes=11))
        Aviso.objects.create(estado=Aviso.ERROR, **nuevo)
        self.assertEqual(reintentar_errores(), 2)

    def test_datos_mal_formados_dan_400_y_no_500(self):
        """Un 500 deja el registro atorado en la cola del celular; un 400 hace que lo descarte."""
        base = {"uuid": str(uuid.uuid4()), "token": firma.firmar(self.conf, self.m), "no_control": "99660002",
                "nip": "1234", "respuestas": [0] * 5, "tiempo_seg": 120}
        for malo in ({"tiempo_seg": "a"}, {"respuestas": ["x"] * 5}, {"respuestas": [{}] * 5},
                     {"capturado_en": 5}):
            with self.subTest(malo=malo):
                r = Client().post("/api/registros", json.dumps({**base, **malo, "uuid": str(uuid.uuid4())}),
                                  content_type="application/json")
                self.assertEqual(r.status_code, 400)
        r = Client().post("/api/registros", "[]", content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Registro.objects.count(), 0)

    def test_paquete_sin_datos_de_alumnos(self):
        j = self.client.get(f"/api/paquete/{self.conf.pk}").json()
        self.assertNotIn("padron", j)
        self.assertNotIn("99660001", json.dumps(j))

    @override_settings(EXPORT_CODIFICACION="cp1252")
    def test_csv_sin_marca_utf8_en_otra_codificacion(self):
        self.registrar("99660001")
        contenido, _ = servicios.generar_csv(servicios.enviar_validos(self.comite), self.se)
        self.assertTrue(contenido.startswith("folio,"))

    def test_panel_solo_qr_desde_el_minuto_actual(self):
        c = Client()
        c.force_login(self.profe)
        r = c.get(f"/profesor/{self.conf.pk}/")
        faltan = firma.minuto_de(self.conf.cierre_dt()) - firma.minuto_actual() + 2
        self.assertLessEqual(r.context["total_qr"], faltan)
        self.assertLess(r.context["total_qr"], len(firma.paquete_qr(self.conf)))


class TS05_Respaldo(TransactionTestCase):
    """NFR-08: respaldar y restaurar con la conexión de Django, en <carpeta de datos>/backups."""

    def test_respaldar_y_restaurar(self):
        import tempfile
        from pathlib import Path
        from django.core.management import call_command
        with tempfile.TemporaryDirectory() as tmp, override_settings(DATOS_DIR=Path(tmp)):
            Bitacora.objects.create(accion="antes", objeto="x")
            call_command("respaldar", stdout=io.StringIO())
            respaldo = next((Path(tmp) / "backups").glob("respaldo_*.sqlite3"))
            Bitacora.objects.create(accion="después", objeto="x")
            call_command("restaurar", respaldo.name, stdout=io.StringIO())
            self.assertEqual(list(Bitacora.objects.values_list("accion", flat=True)), ["antes"])
