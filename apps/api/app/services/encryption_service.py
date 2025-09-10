"""
Servicio de cifrado para datos sensibles en Axonote.
Utiliza Fernet (AES 128 en modo CBC) con claves derivadas usando PBKDF2.
"""

import os
import base64
import hashlib
from typing import Union, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.exceptions import InvalidToken

from app.core.config import settings


class ServicioCifrado:
    """
    Servicio de cifrado simétrico para datos sensibles.
    
    Utiliza:
    - Fernet (AES 128 en modo CBC con HMAC SHA256)
    - PBKDF2 para derivación de claves
    - Salt único por operación de cifrado
    """
    
    def __init__(self, master_key: Optional[str] = None):
        """
        Inicializa el servicio de cifrado.
        
        Args:
            master_key: Clave maestra. Si no se proporciona, usa la del settings.
        """
        self.master_key = (master_key or settings.SECRET_KEY).encode('utf-8')
        
        # Verificar que la clave maestra tenga suficiente entropía
        if len(self.master_key) < 32:
            raise ValueError("La clave maestra debe tener al menos 32 caracteres")
    
    def cifrar_datos(self, datos: Union[str, bytes]) -> str:
        """
        Cifra datos usando Fernet con salt único.
        
        Args:
            datos: Datos a cifrar (string o bytes)
            
        Returns:
            Datos cifrados en base64 (incluye salt + datos cifrados)
            
        Raises:
            ValueError: Si hay error en el cifrado
        """
        try:
            # Convertir a bytes si es necesario
            if isinstance(datos, str):
                datos = datos.encode('utf-8')
            
            # Generar salt único de 16 bytes
            salt = os.urandom(16)
            
            # Derivar clave usando PBKDF2
            clave_derivada = self._generar_clave_derivada(salt)
            
            # Crear instancia Fernet y cifrar
            f = Fernet(clave_derivada)
            datos_cifrados = f.encrypt(datos)
            
            # Combinar salt + datos cifrados y codificar en base64
            resultado = base64.urlsafe_b64encode(salt + datos_cifrados)
            return resultado.decode('utf-8')
            
        except Exception as e:
            raise ValueError(f"Error al cifrar datos: {str(e)}")
    
    def descifrar_datos(self, datos_cifrados: str) -> str:
        """
        Descifra datos previamente cifrados.
        
        Args:
            datos_cifrados: Datos cifrados en base64
            
        Returns:
            Datos descifrados como string
            
        Raises:
            ValueError: Si hay error en el descifrado o datos corruptos
        """
        try:
            # Decodificar de base64
            datos_completos = base64.urlsafe_b64decode(datos_cifrados.encode('utf-8'))
            
            # Verificar longitud mínima (16 bytes salt + datos cifrados)
            if len(datos_completos) < 16:
                raise ValueError("Datos cifrados inválidos: longitud insuficiente")
            
            # Extraer salt (primeros 16 bytes) y datos cifrados
            salt = datos_completos[:16]
            datos_cifrados_bytes = datos_completos[16:]
            
            # Regenerar la misma clave derivada
            clave_derivada = self._generar_clave_derivada(salt)
            
            # Descifrar
            f = Fernet(clave_derivada)
            datos_descifrados = f.decrypt(datos_cifrados_bytes)
            
            return datos_descifrados.decode('utf-8')
            
        except InvalidToken:
            raise ValueError("Error al descifrar: token inválido o datos corruptos")
        except Exception as e:
            raise ValueError(f"Error al descifrar datos: {str(e)}")
    
    def cifrar_datos_bytes(self, datos: bytes) -> bytes:
        """
        Cifra datos bytes y retorna bytes (sin codificación base64).
        
        Args:
            datos: Datos en bytes a cifrar
            
        Returns:
            Datos cifrados en bytes (salt + datos cifrados)
        """
        try:
            # Generar salt único
            salt = os.urandom(16)
            
            # Derivar clave
            clave_derivada = self._generar_clave_derivada(salt)
            
            # Cifrar
            f = Fernet(clave_derivada)
            datos_cifrados = f.encrypt(datos)
            
            # Combinar salt + datos cifrados
            return salt + datos_cifrados
            
        except Exception as e:
            raise ValueError(f"Error al cifrar datos bytes: {str(e)}")
    
    def descifrar_datos_bytes(self, datos_cifrados: bytes) -> bytes:
        """
        Descifra datos bytes previamente cifrados.
        
        Args:
            datos_cifrados: Datos cifrados en bytes
            
        Returns:
            Datos descifrados en bytes
        """
        try:
            # Verificar longitud mínima
            if len(datos_cifrados) < 16:
                raise ValueError("Datos cifrados inválidos: longitud insuficiente")
            
            # Extraer salt y datos
            salt = datos_cifrados[:16]
            datos_cifrados_bytes = datos_cifrados[16:]
            
            # Regenerar clave
            clave_derivada = self._generar_clave_derivada(salt)
            
            # Descifrar
            f = Fernet(clave_derivada)
            return f.decrypt(datos_cifrados_bytes)
            
        except InvalidToken:
            raise ValueError("Error al descifrar: token inválido o datos corruptos")
        except Exception as e:
            raise ValueError(f"Error al descifrar datos bytes: {str(e)}")
    
    def generar_hash_seguro(self, datos: Union[str, bytes]) -> str:
        """
        Genera un hash SHA-256 de los datos.
        
        Args:
            datos: Datos a hashear
            
        Returns:
            Hash SHA-256 en hexadecimal
        """
        if isinstance(datos, str):
            datos = datos.encode('utf-8')
        
        return hashlib.sha256(datos).hexdigest()
    
    def verificar_integridad(self, datos: Union[str, bytes], hash_esperado: str) -> bool:
        """
        Verifica la integridad de datos comparando con un hash.
        
        Args:
            datos: Datos a verificar
            hash_esperado: Hash SHA-256 esperado
            
        Returns:
            True si la integridad es correcta, False si no
        """
        hash_actual = self.generar_hash_seguro(datos)
        return hash_actual == hash_esperado
    
    def _generar_clave_derivada(self, salt: bytes) -> bytes:
        """
        Genera una clave derivada usando PBKDF2.
        
        Args:
            salt: Salt único para la derivación
            
        Returns:
            Clave derivada de 32 bytes codificada en base64 (para Fernet)
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 32 bytes = 256 bits
            salt=salt,
            iterations=100000,  # 100k iteraciones para seguridad
        )
        
        clave_derivada = kdf.derive(self.master_key)
        return base64.urlsafe_b64encode(clave_derivada)
    
    @staticmethod
    def generar_clave_maestra() -> str:
        """
        Genera una nueva clave maestra segura.
        
        Returns:
            Clave maestra de 64 caracteres hexadecimales
        """
        return os.urandom(32).hex()
    
    def rotar_clave(self, datos_cifrados_antiguos: str, nueva_clave_maestra: str) -> str:
        """
        Rota una clave cifrando datos con una nueva clave maestra.
        
        Args:
            datos_cifrados_antiguos: Datos cifrados con la clave anterior
            nueva_clave_maestra: Nueva clave maestra
            
        Returns:
            Datos re-cifrados con la nueva clave
        """
        # Descifrar con la clave actual
        datos_planos = self.descifrar_datos(datos_cifrados_antiguos)
        
        # Crear nuevo servicio con la nueva clave
        nuevo_servicio = ServicioCifrado(nueva_clave_maestra)
        
        # Re-cifrar con la nueva clave
        return nuevo_servicio.cifrar_datos(datos_planos)


class CamposCifrados:
    """
    Mixin para modelos SQLAlchemy que necesitan campos cifrados.
    Proporciona métodos helper para cifrar/descifrar campos automáticamente.
    """
    
    _servicio_cifrado: Optional[ServicioCifrado] = None
    
    @classmethod
    def configurar_cifrado(cls, servicio_cifrado: ServicioCifrado):
        """Configura el servicio de cifrado para la clase."""
        cls._servicio_cifrado = servicio_cifrado
    
    def cifrar_campo(self, valor: str) -> Optional[str]:
        """Cifra un valor de campo."""
        if not valor or not self._servicio_cifrado:
            return None
        return self._servicio_cifrado.cifrar_datos(valor)
    
    def descifrar_campo(self, valor_cifrado: Optional[str]) -> Optional[str]:
        """Descifra un valor de campo."""
        if not valor_cifrado or not self._servicio_cifrado:
            return None
        try:
            return self._servicio_cifrado.descifrar_datos(valor_cifrado)
        except ValueError:
            # Si no se puede descifrar, retornar None
            return None
    
    def _crear_propiedad_cifrada(self, nombre_campo_cifrado: str):
        """
        Crea una propiedad que cifra/descifra automáticamente.
        
        Args:
            nombre_campo_cifrado: Nombre del campo que almacena el valor cifrado
        """
        def getter(self):
            valor_cifrado = getattr(self, nombre_campo_cifrado)
            return self.descifrar_campo(valor_cifrado)
        
        def setter(self, valor):
            valor_cifrado = self.cifrar_campo(valor) if valor else None
            setattr(self, nombre_campo_cifrado, valor_cifrado)
        
        return property(getter, setter)


# Instancia global del servicio de cifrado
servicio_cifrado_global = ServicioCifrado()


def obtener_servicio_cifrado() -> ServicioCifrado:
    """Obtiene la instancia global del servicio de cifrado."""
    return servicio_cifrado_global


def configurar_cifrado_modelos():
    """Configura el cifrado para todos los modelos que lo necesiten."""
    # Importar aquí para evitar imports circulares
    from app.models.usuario import Usuario
    
    # Configurar el servicio de cifrado para los modelos
    CamposCifrados.configurar_cifrado(servicio_cifrado_global)
