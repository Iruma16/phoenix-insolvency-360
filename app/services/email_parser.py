"""
Parser de archivos de email (.eml, .msg) para Phoenix Legal.

FASE 2A: INGESTA MULTI-FORMATO
Objetivo: Extraer contenido de emails con metadatos estructurados.

Casos de uso:
- Comunicaciones con proveedores (evidencia de impagos)
- Notificaciones de embargo
- Avisos de reclamación
- Correspondencia legal

PRINCIPIOS:
- Extraer metadatos completos (From, To, Subject, Date)
- Preservar cuerpo del mensaje (texto plano + HTML)
- Listar attachments (sin procesarlos aquí)
- Retornar ParsingResult compatible con pipeline
"""
from __future__ import annotations

import email
import email.policy
from email import message_from_binary_file, message_from_bytes
from email.message import EmailMessage
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path
import io

try:
    import extract_msg
    HAS_MSG_SUPPORT = True
except ImportError:
    HAS_MSG_SUPPORT = False


class EmailParseResult:
    """
    Resultado del parsing de un email.
    
    Compatible con ParsingResult de ingesta.py
    """
    
    def __init__(
        self,
        texto: str,
        num_paginas: int,
        tipo_documento: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.texto = texto
        self.num_paginas = num_paginas
        self.tipo_documento = tipo_documento
        self.metadata = metadata or {}
        self.page_offsets = None  # Emails no tienen páginas


def parse_eml_stream(file_stream) -> EmailParseResult:
    """
    Parsea un archivo .eml (RFC 822) desde un stream.
    
    Args:
        file_stream: Stream del archivo .eml
        
    Returns:
        EmailParseResult con contenido y metadatos
    """
    try:
        # Leer bytes del stream
        if hasattr(file_stream, 'read'):
            email_bytes = file_stream.read()
        else:
            email_bytes = file_stream
        
        # Parsear email
        msg = email.message_from_bytes(email_bytes, policy=email.policy.default)
        
        # Extraer metadatos
        from_addr = msg.get('From', 'Unknown')
        to_addr = msg.get('To', 'Unknown')
        subject = msg.get('Subject', 'Sin asunto')
        date_str = msg.get('Date', '')
        
        # Parsear fecha
        email_date = None
        if date_str:
            try:
                from email.utils import parsedate_to_datetime
                email_date = parsedate_to_datetime(date_str)
            except Exception:
                pass
        
        # Extraer cuerpo del mensaje
        body_text = ""
        body_html = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                
                if content_type == 'text/plain':
                    try:
                        body_text += part.get_content()
                    except Exception:
                        pass
                elif content_type == 'text/html':
                    try:
                        body_html += part.get_content()
                    except Exception:
                        pass
        else:
            # Email simple (no multipart)
            content_type = msg.get_content_type()
            if content_type == 'text/plain':
                body_text = msg.get_content()
            elif content_type == 'text/html':
                body_html = msg.get_content()
        
        # Preferir texto plano, fallback a HTML
        body = body_text if body_text else body_html
        
        # Construir texto completo con metadatos
        texto_completo = f"""EMAIL
De: {from_addr}
Para: {to_addr}
Asunto: {subject}
Fecha: {date_str}

--- CUERPO DEL MENSAJE ---
{body}
"""
        
        # Listar attachments
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    filename = part.get_filename()
                    if filename:
                        attachments.append(filename)
        
        # Metadata estructurada
        metadata = {
            'from': from_addr,
            'to': to_addr,
            'subject': subject,
            'date': email_date.isoformat() if email_date else date_str,
            'attachments': attachments,
            'has_attachments': len(attachments) > 0,
            'body_length': len(body),
        }
        
        print(f"✅ [EMAIL] Email parseado exitosamente")
        print(f"✅ [EMAIL] - De: {from_addr}")
        print(f"✅ [EMAIL] - Asunto: {subject}")
        print(f"✅ [EMAIL] - Attachments: {len(attachments)}")
        print(f"✅ [EMAIL] - Caracteres: {len(texto_completo)}")
        
        return EmailParseResult(
            texto=texto_completo,
            num_paginas=1,  # Email = 1 "página"
            tipo_documento="email",
            metadata=metadata,
        )
        
    except Exception as e:
        print(f"❌ [EMAIL] Error parseando .eml: {e}")
        return EmailParseResult(
            texto="",
            num_paginas=0,
            tipo_documento="email",
            metadata={'error': str(e)},
        )


def parse_msg_stream(file_stream, filename: str) -> EmailParseResult:
    """
    Parsea un archivo .msg (Outlook) desde un stream.
    
    Args:
        file_stream: Stream del archivo .msg
        filename: Nombre del archivo (para logging)
        
    Returns:
        EmailParseResult con contenido y metadatos
    """
    if not HAS_MSG_SUPPORT:
        print("❌ [EMAIL] extract-msg no instalado, no se puede parsear .msg")
        return EmailParseResult(
            texto="ERROR: extract-msg no disponible",
            num_paginas=0,
            tipo_documento="email",
            metadata={'error': 'extract-msg not installed'},
        )
    
    try:
        # extract-msg requiere archivo en disco o bytes
        if hasattr(file_stream, 'read'):
            msg_bytes = file_stream.read()
        else:
            msg_bytes = file_stream
        
        # Guardar temporalmente (extract-msg no soporta streams directamente)
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.msg') as tmp:
            tmp.write(msg_bytes)
            tmp_path = tmp.name
        
        try:
            # Parsear con extract-msg
            msg = extract_msg.Message(tmp_path)
            
            from_addr = msg.sender or 'Unknown'
            to_addr = msg.to or 'Unknown'
            subject = msg.subject or 'Sin asunto'
            date_str = str(msg.date) if msg.date else ''
            body = msg.body or ''
            
            # Construir texto completo
            texto_completo = f"""EMAIL (Outlook .msg)
De: {from_addr}
Para: {to_addr}
Asunto: {subject}
Fecha: {date_str}

--- CUERPO DEL MENSAJE ---
{body}
"""
            
            # Listar attachments
            attachments = [att.longFilename or att.shortFilename for att in msg.attachments]
            
            metadata = {
                'from': from_addr,
                'to': to_addr,
                'subject': subject,
                'date': date_str,
                'attachments': attachments,
                'has_attachments': len(attachments) > 0,
                'body_length': len(body),
            }
            
            print(f"✅ [EMAIL] Email .msg parseado exitosamente")
            print(f"✅ [EMAIL] - De: {from_addr}")
            print(f"✅ [EMAIL] - Asunto: {subject}")
            print(f"✅ [EMAIL] - Attachments: {len(attachments)}")
            
            msg.close()
            
            return EmailParseResult(
                texto=texto_completo,
                num_paginas=1,
                tipo_documento="email",
                metadata=metadata,
            )
            
        finally:
            # Limpiar archivo temporal
            import os
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        
    except Exception as e:
        print(f"❌ [EMAIL] Error parseando .msg: {e}")
        return EmailParseResult(
            texto="",
            num_paginas=0,
            tipo_documento="email",
            metadata={'error': str(e)},
        )


def parse_email_file(file_path: str) -> EmailParseResult:
    """
    Parsea un archivo de email desde ruta de archivo.
    
    Args:
        file_path: Ruta al archivo .eml o .msg
        
    Returns:
        EmailParseResult
    """
    path = Path(file_path)
    
    with open(path, 'rb') as f:
        if path.suffix.lower() == '.eml':
            return parse_eml_stream(f)
        elif path.suffix.lower() == '.msg':
            return parse_msg_stream(f, path.name)
        else:
            raise ValueError(f"Formato de email no soportado: {path.suffix}")
