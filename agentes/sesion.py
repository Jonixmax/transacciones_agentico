"""SESIÓN: estado compartido entre agentes y skills (datos cargados, límites, carpeta de salida)."""
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from nucleo.procesador import procesar_archivo


@dataclass
class Sesion:
    reglas: Any
    resultado: Any = None
    ruta: Optional[str] = None
    max_filas: int = 10
    directorio_salida: str = field(default_factory=os.getcwd)   # base para las exportaciones

    @property
    def tiene_datos(self):
        return self.resultado is not None

    def cargar_archivo(self, ruta):
        """Carga y procesa un archivo. Lanza DatosError si falla (y conserva los datos previos)."""
        self.resultado = procesar_archivo(ruta, self.reglas)
        self.ruta = ruta
