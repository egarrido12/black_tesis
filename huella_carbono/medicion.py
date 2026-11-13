"""Medición de huella de carbono con CodeCarbon, durante y al final de cada fase.

Lo comparten rope_pruebas/ y llm_pruebas/. Cada fase (una operación de Rope,
una llamada a Claude, una corrida de pytest...) se mide con dos trackers de
CodeCarbon en paralelo:

  - "maquina" (tracking_mode='machine'): toda la computadora, incluido el
    consumo de fondo del sistema operativo y otras aplicaciones.
  - "proceso" (tracking_mode='process'): solo este proceso de Python y sus
    hijos (pytest), es decir, lo atribuible al experimento.

Además del total al terminar la fase, se guarda lo que pasa MIENTRAS corre:

  - serie_temporal_<modo>.csv: una fila por cada muestra de CodeCarbon (cada
    `intervalo_s` segundos), con la energía de esa muestra, la acumulada y la
    potencia media. Se obtiene con la vía oficial de CodeCarbon para salidas
    en vivo: un output handler propio (BaseOutput.live_out) con
    api_call_interval=1, que CodeCarbon llama después de cada medición.
  - eventos.csv: marcas de tiempo dentro de una fase (por ejemplo
    "primer_token" de Claude o "cambios_calculados" de Rope), para ubicar en la
    serie temporal qué estaba pasando.
  - emisiones_<modo>.csv: el CSV estándar de CodeCarbon, una fila por fase.

Uso:
    medidor = Medidor(carpeta_resultados, pais='COL')
    registro = {}
    with medidor.medir('02_rename_rope', registro) as m:
        ...
        m.marcar('cambios_calculados')
    registro['proceso']['energia_Wh']
"""
import contextlib
import csv
import time
from datetime import datetime

import codecarbon
from codecarbon import OfflineEmissionsTracker
from codecarbon.output_methods.base_output import BaseOutput

MODOS = {'maquina': 'machine', 'proceso': 'process'}

COLUMNAS_SERIE = ['fase', 't_s', 'hora', 'duracion_muestra_s', 'energia_muestra_mWh',
                  'energia_acumulada_mWh', 'potencia_media_W', 'potencia_cpu_W',
                  'potencia_ram_W', 'emisiones_acumuladas_mg']


class SerieTemporal(BaseOutput):
    """Output handler de CodeCarbon que guarda cada muestra mientras el tracker corre."""

    def __init__(self, ruta, fase):
        self.ruta = ruta
        self.fase = fase
        self.t0 = time.perf_counter()
        self.muestras = []

    def live_out(self, total, delta):
        # delta.energy_consumed está en kWh: kWh * 3.6e6 = J; J / s = W.
        potencia = (delta.energy_consumed * 3.6e6 / delta.duration) if delta.duration else 0.0
        fila = {
            'fase': self.fase,
            't_s': round(time.perf_counter() - self.t0, 3),
            'hora': datetime.now().isoformat(timespec='milliseconds'),
            'duracion_muestra_s': round(delta.duration, 3),
            'energia_muestra_mWh': delta.energy_consumed * 1e6,
            'energia_acumulada_mWh': total.energy_consumed * 1e6,
            'potencia_media_W': potencia,
            'potencia_cpu_W': total.cpu_power,
            'potencia_ram_W': total.ram_power,
            'emisiones_acumuladas_mg': total.emissions * 1e6,
        }
        self.muestras.append(fila)
        nuevo = not self.ruta.exists()
        with self.ruta.open('a', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=COLUMNAS_SERIE)
            if nuevo:
                escritor.writeheader()
            escritor.writerow(fila)

    def out(self, total, delta):
        pass


def datos_tracker(d, serie):
    """Convierte el EmissionsData de CodeCarbon en un dict con unidades útiles."""
    potencias = [m['potencia_media_W'] for m in serie.muestras]
    return {
        'duracion_s': round(d.duration, 3),
        'energia_Wh': d.energy_consumed * 1000,
        'energia_cpu_Wh': d.cpu_energy * 1000,
        'energia_ram_Wh': d.ram_energy * 1000,
        'emisiones_mgCO2eq': d.emissions * 1e6,
        'potencia_cpu_W': d.cpu_power,
        'potencia_ram_W': d.ram_power,
        'agua_L': getattr(d, 'water_consumed', None),
        'muestras': len(serie.muestras),
        'potencia_max_W': max(potencias) if potencias else None,
    }


class Medidor:
    def __init__(self, carpeta, pais='COL', intervalo_s=0.25):
        self.carpeta = carpeta
        self.pais = pais
        self.intervalo_s = intervalo_s
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._fases = []  # pila de (nombre, t0) para marcar() dentro de fases anidadas

    @contextlib.contextmanager
    def medir(self, nombre, registro, intervalo_s=None):
        """Mide el bloque `with` con los dos modos, durante y al final.

        Al salir, `registro` queda con una clave por modo ('maquina', 'proceso').
        """
        intervalo = intervalo_s or self.intervalo_s
        series = {}
        trackers = {}
        for etiqueta, modo in MODOS.items():
            series[etiqueta] = SerieTemporal(
                self.carpeta / ('serie_temporal_%s.csv' % etiqueta), nombre)
            trackers[etiqueta] = OfflineEmissionsTracker(
                project_name=nombre,
                country_iso_code=self.pais,
                tracking_mode=modo,
                measure_power_secs=intervalo,
                api_call_interval=1,
                output_handlers=[series[etiqueta]],
                output_dir=str(self.carpeta),
                output_file='emisiones_%s.csv' % etiqueta,
                save_to_file=True,
                log_level='error',
                allow_multiple_runs=True,
            )
        for t in trackers.values():
            t.start()
        self._fases.append((nombre, time.perf_counter()))
        try:
            yield self
        finally:
            self._fases.pop()
            for etiqueta, t in trackers.items():
                t.stop()
                registro[etiqueta] = datos_tracker(t.final_emissions_data, series[etiqueta])

    def marcar(self, evento, detalle=''):
        """Anota en eventos.csv un momento dentro de la fase más interna en curso."""
        fase, t0 = self._fases[-1]
        ruta = self.carpeta / 'eventos.csv'
        nuevo = not ruta.exists()
        with ruta.open('a', newline='') as f:
            escritor = csv.writer(f)
            if nuevo:
                escritor.writerow(['fase', 't_s', 'hora', 'evento', 'detalle'])
            escritor.writerow([fase, round(time.perf_counter() - t0, 3),
                               datetime.now().isoformat(timespec='milliseconds'),
                               evento, detalle])

    def info(self):
        """Metadatos de la medición (hardware detectado, factor de emisión)."""
        t = OfflineEmissionsTracker(country_iso_code=self.pais, save_to_file=False,
                                    log_level='error', allow_multiple_runs=True)
        t.start()
        time.sleep(1)
        t.stop()
        d = t.final_emissions_data
        return {
            'codecarbon': codecarbon.__version__,
            'pais': d.country_name,
            'pais_iso': self.pais,
            'intensidad_gCO2eq_kWh': round(d.emissions / d.energy_consumed * 1000, 3),
            'cpu': d.cpu_model,
            'cpu_count': d.cpu_count,
            'ram_GB': round(d.ram_total_size, 1),
            'os': d.os,
            'metodo_cpu': 'cpu_load (TDP x carga de CPU; sin sensores de energía)',
            'intervalo_muestreo_s': self.intervalo_s,
        }
