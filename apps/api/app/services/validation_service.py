"""
Servicio de validación de entrada y sanitización para Axonote.
Proporciona validación robusta y sanitización de datos de entrada.
"""

import re
import html
import bleach
import unicodedata
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse
from email_validator import validate_email, EmailNotValidError
from pydantic import BaseModel, ValidationError, validator
from fastapi import HTTPException, status

from app.core.config import settings


class ValidacionError(Exception):
    """Excepción personalizada para errores de validación."""
    
    def __init__(self, mensaje: str, campo: Optional[str] = None, codigo: str = "VALIDATION_ERROR"):
        self.mensaje = mensaje
        self.campo = campo
        self.codigo = codigo
        super().__init__(mensaje)


class ServicioValidacion:
    """
    Servicio completo de validación y sanitización de datos.
    Proporciona validaciones específicas para el contexto médico.
    """
    
    def __init__(self):
        # Configuración de bleach para sanitización HTML
        self.allowed_tags = [
            'p', 'br', 'strong', 'em', 'u', 'ol', 'ul', 'li',
            'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote'
        ]
        
        self.allowed_attributes = {
            '*': ['class'],
            'a': ['href', 'title'],
        }
        
        # Patrones regex comunes
        self.patrones = {
            'email': re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'),
            'telefono': re.compile(r'^\+?[1-9]\d{1,14}$'),
            'nombre': re.compile(r'^[a-zA-ZÀ-ÿ\u00f1\u00d1\s\-\'\.]{2,100}$'),
            'password_seguro': re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{12,}$'),
            'sql_injection': re.compile(r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)', re.IGNORECASE),
            'xss_basico': re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),
            'path_traversal': re.compile(r'\.\./|\.\.\\'),
            'comando_injection': re.compile(r'[;&|`$(){}[\]<>]'),
        }
    
    def validar_email(self, email: str) -> str:
        """
        Valida y normaliza una dirección de email.
        
        Args:
            email: Email a validar
            
        Returns:
            Email normalizado
            
        Raises:
            ValidacionError: Si el email no es válido
        """
        
        if not email or not isinstance(email, str):
            raise ValidacionError("Email requerido", "email", "EMAIL_REQUIRED")
        
        # Sanitizar entrada básica
        email = self.sanitizar_string_basico(email.strip().lower())
        
        # Validar longitud
        if len(email) > 254:  # RFC 5321 límite
            raise ValidacionError("Email demasiado largo", "email", "EMAIL_TOO_LONG")
        
        try:
            # Validar con email-validator
            validation_result = validate_email(email)
            return validation_result.email
        except EmailNotValidError as e:
            raise ValidacionError(f"Email inválido: {str(e)}", "email", "EMAIL_INVALID")
    
    def validar_password(self, password: str) -> bool:
        """
        Valida la fortaleza de una contraseña.
        
        Args:
            password: Contraseña a validar
            
        Returns:
            True si es válida
            
        Raises:
            ValidacionError: Si la contraseña no cumple los requisitos
        """
        
        if not password or not isinstance(password, str):
            raise ValidacionError("Contraseña requerida", "password", "PASSWORD_REQUIRED")
        
        # Verificar longitud mínima
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            raise ValidacionError(
                f"La contraseña debe tener al menos {settings.PASSWORD_MIN_LENGTH} caracteres",
                "password",
                "PASSWORD_TOO_SHORT"
            )
        
        # Verificar longitud máxima (prevenir ataques DoS)
        if len(password) > 128:
            raise ValidacionError(
                "La contraseña es demasiado larga",
                "password",
                "PASSWORD_TOO_LONG"
            )
        
        errores = []
        
        # Verificar mayúsculas
        if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
            errores.append("al menos una letra mayúscula")
        
        # Verificar minúsculas
        if settings.PASSWORD_REQUIRE_LOWERCASE and not any(c.islower() for c in password):
            errores.append("al menos una letra minúscula")
        
        # Verificar números
        if settings.PASSWORD_REQUIRE_NUMBERS and not any(c.isdigit() for c in password):
            errores.append("al menos un número")
        
        # Verificar caracteres especiales
        if settings.PASSWORD_REQUIRE_SPECIAL:
            caracteres_especiales = "!@#$%^&*()_+-=[]{}|;:,.<>?/~`"
            if not any(c in caracteres_especiales for c in password):
                errores.append("al menos un carácter especial")
        
        # Verificar patrones comunes débiles
        patrones_debiles = [
            r'(.)\1{3,}',  # Más de 3 caracteres repetidos
            r'(012|123|234|345|456|567|678|789|890)',  # Secuencias numéricas
            r'(abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)',  # Secuencias alfabéticas
            r'(qwerty|asdfgh|zxcvbn)',  # Patrones de teclado
        ]
        
        for patron in patrones_debiles:
            if re.search(patron, password.lower()):
                errores.append("no debe contener patrones comunes o secuencias")
                break
        
        if errores:
            mensaje = f"La contraseña debe contener: {', '.join(errores)}"
            raise ValidacionError(mensaje, "password", "PASSWORD_WEAK")
        
        return True
    
    def validar_nombre_completo(self, nombre: str) -> str:
        """
        Valida y sanitiza un nombre completo.
        
        Args:
            nombre: Nombre a validar
            
        Returns:
            Nombre sanitizado
            
        Raises:
            ValidacionError: Si el nombre no es válido
        """
        
        if not nombre or not isinstance(nombre, str):
            raise ValidacionError("Nombre completo requerido", "nombre_completo", "NAME_REQUIRED")
        
        # Sanitizar y normalizar
        nombre = self.sanitizar_string_basico(nombre.strip())
        nombre = self.normalizar_unicode(nombre)
        
        # Verificar longitud
        if len(nombre) < 2:
            raise ValidacionError("El nombre debe tener al menos 2 caracteres", "nombre_completo", "NAME_TOO_SHORT")
        
        if len(nombre) > 100:
            raise ValidacionError("El nombre es demasiado largo", "nombre_completo", "NAME_TOO_LONG")
        
        # Verificar patrón
        if not self.patrones['nombre'].match(nombre):
            raise ValidacionError(
                "El nombre contiene caracteres no válidos",
                "nombre_completo",
                "NAME_INVALID_CHARS"
            )
        
        # Verificar que no sea solo espacios o caracteres especiales
        if not any(c.isalpha() for c in nombre):
            raise ValidacionError(
                "El nombre debe contener al menos una letra",
                "nombre_completo",
                "NAME_NO_LETTERS"
            )
        
        return nombre.title()  # Capitalizar correctamente
    
    def validar_texto_medico(self, texto: str, max_length: int = 10000) -> str:
        """
        Valida y sanitiza texto médico (transcripciones, notas, etc.).
        
        Args:
            texto: Texto a validar
            max_length: Longitud máxima permitida
            
        Returns:
            Texto sanitizado
            
        Raises:
            ValidacionError: Si el texto no es válido
        """
        
        if not texto or not isinstance(texto, str):
            return ""
        
        # Sanitizar HTML y scripts
        texto = self.sanitizar_html(texto)
        
        # Verificar longitud
        if len(texto) > max_length:
            raise ValidacionError(
                f"El texto excede la longitud máxima de {max_length} caracteres",
                "texto",
                "TEXT_TOO_LONG"
            )
        
        # Verificar inyecciones SQL
        if self.patrones['sql_injection'].search(texto):
            raise ValidacionError(
                "El texto contiene patrones sospechosos",
                "texto",
                "TEXT_SUSPICIOUS_CONTENT"
            )
        
        # Normalizar espacios en blanco
        texto = re.sub(r'\s+', ' ', texto).strip()
        
        return texto
    
    def validar_url(self, url: str) -> str:
        """
        Valida y sanitiza una URL.
        
        Args:
            url: URL a validar
            
        Returns:
            URL sanitizada
            
        Raises:
            ValidacionError: Si la URL no es válida
        """
        
        if not url or not isinstance(url, str):
            raise ValidacionError("URL requerida", "url", "URL_REQUIRED")
        
        # Sanitizar entrada básica
        url = self.sanitizar_string_basico(url.strip())
        
        # Verificar longitud
        if len(url) > 2048:
            raise ValidacionError("URL demasiado larga", "url", "URL_TOO_LONG")
        
        try:
            parsed = urlparse(url)
            
            # Verificar esquema
            if parsed.scheme not in ['http', 'https']:
                raise ValidacionError("Esquema de URL no permitido", "url", "URL_INVALID_SCHEME")
            
            # Verificar que tenga dominio
            if not parsed.netloc:
                raise ValidacionError("URL debe tener un dominio válido", "url", "URL_NO_DOMAIN")
            
            # Verificar path traversal
            if self.patrones['path_traversal'].search(url):
                raise ValidacionError("URL contiene path traversal", "url", "URL_PATH_TRAVERSAL")
            
            return url
            
        except Exception as e:
            raise ValidacionError(f"URL inválida: {str(e)}", "url", "URL_INVALID")
    
    def validar_json_estructura(self, data: Any, esquema_esperado: Dict) -> Dict:
        """
        Valida que un JSON tenga la estructura esperada.
        
        Args:
            data: Datos a validar
            esquema_esperado: Esquema esperado con tipos y validaciones
            
        Returns:
            Datos validados
            
        Raises:
            ValidacionError: Si la estructura no es válida
        """
        
        if not isinstance(data, dict):
            raise ValidacionError("Se esperaba un objeto JSON", "data", "JSON_NOT_OBJECT")
        
        datos_validados = {}
        
        for campo, config in esquema_esperado.items():
            valor = data.get(campo)
            
            # Verificar campos requeridos
            if config.get('required', False) and valor is None:
                raise ValidacionError(f"Campo requerido: {campo}", campo, "FIELD_REQUIRED")
            
            if valor is not None:
                # Verificar tipo
                tipo_esperado = config.get('type')
                if tipo_esperado and not isinstance(valor, tipo_esperado):
                    raise ValidacionError(
                        f"Tipo incorrecto para {campo}: esperado {tipo_esperado.__name__}",
                        campo,
                        "FIELD_WRONG_TYPE"
                    )
                
                # Verificar longitud para strings
                if isinstance(valor, str):
                    min_length = config.get('min_length', 0)
                    max_length = config.get('max_length', float('inf'))
                    
                    if len(valor) < min_length:
                        raise ValidacionError(
                            f"Campo {campo} demasiado corto (mínimo {min_length})",
                            campo,
                            "FIELD_TOO_SHORT"
                        )
                    
                    if len(valor) > max_length:
                        raise ValidacionError(
                            f"Campo {campo} demasiado largo (máximo {max_length})",
                            campo,
                            "FIELD_TOO_LONG"
                        )
                    
                    # Sanitizar string
                    valor = self.sanitizar_string_basico(valor)
                
                # Verificar valores permitidos
                valores_permitidos = config.get('allowed_values')
                if valores_permitidos and valor not in valores_permitidos:
                    raise ValidacionError(
                        f"Valor no permitido para {campo}",
                        campo,
                        "FIELD_VALUE_NOT_ALLOWED"
                    )
                
                # Aplicar validador personalizado
                validador = config.get('validator')
                if validador and callable(validador):
                    try:
                        valor = validador(valor)
                    except Exception as e:
                        raise ValidacionError(
                            f"Validación fallida para {campo}: {str(e)}",
                            campo,
                            "FIELD_VALIDATION_FAILED"
                        )
                
                datos_validados[campo] = valor
        
        return datos_validados
    
    def sanitizar_string_basico(self, texto: str) -> str:
        """
        Sanitización básica de strings.
        
        Args:
            texto: Texto a sanitizar
            
        Returns:
            Texto sanitizado
        """
        
        if not isinstance(texto, str):
            return str(texto)
        
        # Remover caracteres de control
        texto = ''.join(char for char in texto if ord(char) >= 32 or char in '\t\n\r')
        
        # Escapar HTML básico
        texto = html.escape(texto)
        
        # Remover patrones de inyección de comandos
        if self.patrones['comando_injection'].search(texto):
            # Remover caracteres peligrosos
            texto = re.sub(r'[;&|`$(){}[\]<>]', '', texto)
        
        return texto
    
    def sanitizar_html(self, texto: str) -> str:
        """
        Sanitiza HTML permitiendo solo tags seguros.
        
        Args:
            texto: HTML a sanitizar
            
        Returns:
            HTML sanitizado
        """
        
        if not isinstance(texto, str):
            return str(texto)
        
        # Usar bleach para sanitizar HTML
        texto_limpio = bleach.clean(
            texto,
            tags=self.allowed_tags,
            attributes=self.allowed_attributes,
            strip=True
        )
        
        return texto_limpio
    
    def normalizar_unicode(self, texto: str) -> str:
        """
        Normaliza texto Unicode para consistencia.
        
        Args:
            texto: Texto a normalizar
            
        Returns:
            Texto normalizado
        """
        
        if not isinstance(texto, str):
            return str(texto)
        
        # Normalizar a NFC (Canonical Decomposition, followed by Canonical Composition)
        texto_normalizado = unicodedata.normalize('NFC', texto)
        
        return texto_normalizado
    
    def validar_archivo_upload(
        self,
        filename: str,
        content_type: str,
        file_size: int,
        extensiones_permitidas: List[str],
        tamaño_maximo_mb: int = 100
    ) -> Dict[str, Any]:
        """
        Valida un archivo subido.
        
        Args:
            filename: Nombre del archivo
            content_type: Tipo MIME
            file_size: Tamaño en bytes
            extensiones_permitidas: Lista de extensiones permitidas
            tamaño_maximo_mb: Tamaño máximo en MB
            
        Returns:
            Dict con información del archivo validado
            
        Raises:
            ValidacionError: Si el archivo no es válido
        """
        
        if not filename:
            raise ValidacionError("Nombre de archivo requerido", "filename", "FILENAME_REQUIRED")
        
        # Sanitizar nombre de archivo
        filename_sanitizado = self.sanitizar_nombre_archivo(filename)
        
        # Verificar extensión
        if '.' not in filename_sanitizado:
            raise ValidacionError("Archivo debe tener extensión", "filename", "NO_EXTENSION")
        
        extension = filename_sanitizado.lower().split('.')[-1]
        if extension not in [ext.lower() for ext in extensiones_permitidas]:
            raise ValidacionError(
                f"Extensión no permitida. Permitidas: {', '.join(extensiones_permitidas)}",
                "filename",
                "EXTENSION_NOT_ALLOWED"
            )
        
        # Verificar tamaño
        tamaño_maximo_bytes = tamaño_maximo_mb * 1024 * 1024
        if file_size > tamaño_maximo_bytes:
            raise ValidacionError(
                f"Archivo demasiado grande. Máximo: {tamaño_maximo_mb}MB",
                "file_size",
                "FILE_TOO_LARGE"
            )
        
        if file_size <= 0:
            raise ValidacionError("Archivo vacío", "file_size", "FILE_EMPTY")
        
        # Verificar tipo MIME básico
        tipos_mime_audio = [
            "audio/wav", "audio/wave", "audio/x-wav",
            "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a",
            "audio/flac", "audio/x-flac", "audio/ogg", "audio/vorbis"
        ]
        
        tipos_mime_imagen = [
            "image/jpeg", "image/jpg", "image/png", "image/webp"
        ]
        
        if extension in ['wav', 'mp3', 'mp4', 'm4a', 'flac', 'ogg']:
            if content_type not in tipos_mime_audio:
                raise ValidacionError(
                    f"Tipo MIME no válido para audio: {content_type}",
                    "content_type",
                    "INVALID_MIME_TYPE"
                )
        
        elif extension in ['jpg', 'jpeg', 'png', 'webp']:
            if content_type not in tipos_mime_imagen:
                raise ValidacionError(
                    f"Tipo MIME no válido para imagen: {content_type}",
                    "content_type",
                    "INVALID_MIME_TYPE"
                )
        
        return {
            "filename_original": filename,
            "filename_sanitizado": filename_sanitizado,
            "extension": extension,
            "content_type": content_type,
            "file_size": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2)
        }
    
    def sanitizar_nombre_archivo(self, filename: str) -> str:
        """
        Sanitiza un nombre de archivo.
        
        Args:
            filename: Nombre original del archivo
            
        Returns:
            Nombre sanitizado
        """
        
        if not isinstance(filename, str):
            filename = str(filename)
        
        # Normalizar Unicode
        filename = self.normalizar_unicode(filename)
        
        # Remover caracteres peligrosos
        filename = re.sub(r'[^\w\s.-]', '', filename)
        
        # Remover múltiples espacios y puntos
        filename = re.sub(r'\s+', '_', filename)
        filename = re.sub(r'\.+', '.', filename)
        
        # Remover path traversal
        filename = filename.replace('..', '').replace('/', '').replace('\\', '')
        
        # Limitar longitud
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            max_name_length = 255 - len(ext) - 1 if ext else 255
            filename = name[:max_name_length] + ('.' + ext if ext else '')
        
        return filename.strip()
    
    def crear_validador_pydantic(self, esquema: Dict) -> BaseModel:
        """
        Crea un validador Pydantic dinámico basado en un esquema.
        
        Args:
            esquema: Esquema de validación
            
        Returns:
            Clase BaseModel para validación
        """
        
        class ValidadorDinamico(BaseModel):
            pass
        
        # Añadir campos dinámicamente
        for campo, config in esquema.items():
            tipo = config.get('type', str)
            requerido = config.get('required', False)
            
            if requerido:
                setattr(ValidadorDinamico, campo, (tipo, ...))
            else:
                setattr(ValidadorDinamico, campo, (Optional[tipo], None))
        
        return ValidadorDinamico


# Instancia global del servicio
servicio_validacion = ServicioValidacion()


def validar_entrada_api(data: Any, esquema: Dict) -> Dict:
    """
    Función helper para validar entrada de API.
    
    Args:
        data: Datos a validar
        esquema: Esquema de validación
        
    Returns:
        Datos validados
        
    Raises:
        HTTPException: Si la validación falla
    """
    
    try:
        return servicio_validacion.validar_json_estructura(data, esquema)
    except ValidacionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Validation failed",
                "message": e.mensaje,
                "field": e.campo,
                "code": e.codigo
            }
        )
