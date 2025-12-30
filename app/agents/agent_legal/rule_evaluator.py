"""
Evaluador seguro de expresiones lógicas para el motor de reglas.
"""

import operator
from typing import Any, Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class RuleEvaluator:
    """Evaluador seguro de expresiones lógicas."""

    def __init__(self, variables: Dict[str, Any]):
        """
        Inicializa el evaluador con variables del caso.

        Args:
            variables: Diccionario con variables del caso
        """
        self.variables = variables
        self.operators = {
            '==': operator.eq,
            '!=': operator.ne,
            '>': operator.gt,
            '<': operator.lt,
            '>=': operator.ge,
            '<=': operator.le,
            'AND': lambda a, b: a and b,
            'OR': lambda a, b: a or b,
            'NOT': lambda a: not a,
        }
        self.functions = {
            'MIN': min,
            'MAX': max,
            'COUNT': len,
            'SUM': sum,
        }

    def _tokenize(self, expression: str) -> List[str]:
        """Tokeniza una expresión separando operadores, valores y funciones."""
        # Validación defensiva
        if not isinstance(expression, str):
            raise TypeError(f"Expression must be string, got {type(expression)}")
        
        tokens = []
        current = ''
        i = 0
        
        while i < len(expression):
            char = expression[i]
            
            if char.isspace():
                if current:
                    tokens.append(current)
                    current = ''
            elif char in '()':
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append(char)
            elif expression[i:i+3] == 'AND':
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append('AND')
                i += 2
            elif expression[i:i+3] == 'NOT':
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append('NOT')
                i += 2
            elif expression[i:i+5] == 'COUNT':
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append('COUNT')
                i += 4
            elif expression[i:i+3] in ('MIN', 'MAX', 'SUM'):
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append(expression[i:i+3])
                i += 2
            elif expression[i:i+2] in ('==', '!=', '>=', '<='):
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append(expression[i:i+2])
                i += 1
            elif expression[i:i+2] == 'OR':
                if current:
                    tokens.append(current)
                    current = ''
                tokens.append('OR')
                i += 1
            else:
                current += char
            
            i += 1
        
        if current:
            tokens.append(current)
        
        return tokens

    def _resolve_value(self, token: str) -> Any:
        """Resuelve un token a su valor."""
        token = token.strip()
        
        if token in ('True', 'true'):
            return True
        if token in ('False', 'false'):
            return False
        if token == 'null':
            return None
        
        if token.startswith('"') or token.startswith("'"):
            return token[1:-1]
        
        if token.replace('.', '', 1).replace('-', '', 1).isdigit():
            if '.' in token:
                return float(token)
            return int(token)
        
        if token in self.variables:
            return self.variables[token]
        
        return None

    def _evaluate_expression(self, tokens: List[str]) -> Any:
        """Evalúa una expresión tokenizada."""
        if not tokens:
            return None
        
        tokens = tokens.copy()
        
        while '(' in tokens:
            start = None
            func_name = None
            
            for i, token in enumerate(tokens):
                if token in self.functions and i + 1 < len(tokens) and tokens[i + 1] == '(':
                    func_name = token
                    start = i
                    break
            
            if start is None:
                start = len(tokens) - 1 - tokens[::-1].index('(')
                end = start + 1
                depth = 1
                
                while end < len(tokens) and depth > 0:
                    if tokens[end] == '(':
                        depth += 1
                    elif tokens[end] == ')':
                        depth -= 1
                    end += 1
                
                if depth == 0:
                    inner = tokens[start+1:end-1]
                    result = self._evaluate_expression(inner)
                    tokens = tokens[:start] + [result] + tokens[end:]
                    continue
            else:
                end = start + 2
                depth = 1
                
                while end < len(tokens) and depth > 0:
                    if tokens[end] == '(':
                        depth += 1
                    elif tokens[end] == ')':
                        depth -= 1
                    end += 1
                
                if depth == 0:
                    inner_tokens = tokens[start+2:end-1]
                    args = []
                    current_arg = []
                    arg_depth = 0
                    
                    for tok in inner_tokens:
                        if tok == '(':
                            arg_depth += 1
                            current_arg.append(tok)
                        elif tok == ')':
                            arg_depth -= 1
                            current_arg.append(tok)
                        elif tok == ',' and arg_depth == 0:
                            if current_arg:
                                args.append(self._evaluate_expression(current_arg))
                                current_arg = []
                        else:
                            current_arg.append(tok)
                    
                    if current_arg:
                        args.append(self._evaluate_expression(current_arg))
                    
                    func = self.functions[func_name]
                    try:
                        if func_name in ('MIN', 'MAX'):
                            resolved_args = []
                            for arg in args:
                                val = self._evaluate_expression([arg]) if isinstance(arg, list) else self._resolve_value(str(arg))
                                if val is not None:
                                    resolved_args.append(val)
                            result = func(resolved_args) if resolved_args else None
                        elif func_name == 'COUNT':
                            if args:
                                resolved_arg = self._evaluate_expression(args[0]) if isinstance(args[0], list) else self._resolve_value(str(args[0]))
                                if isinstance(resolved_arg, (list, tuple)):
                                    result = func(resolved_arg)
                                else:
                                    result = 1 if resolved_arg is not None else 0
                            else:
                                result = 0
                        elif func_name == 'SUM':
                            resolved_args = []
                            for arg in args:
                                val = self._evaluate_expression([arg]) if isinstance(arg, list) else self._resolve_value(str(arg))
                                if val is not None and isinstance(val, (int, float)):
                                    resolved_args.append(val)
                            result = func(resolved_args) if resolved_args else 0
                        else:
                            result = func(*args)
                    except Exception as e:
                        logger.warning(f"Error ejecutando función {func_name}: {e}")
                        result = None
                    
                    tokens = tokens[:start] + [result] + tokens[end:]
                    continue
        
        while len(tokens) > 1:
            if 'NOT' in tokens:
                idx = tokens.index('NOT')
                if idx + 1 < len(tokens):
                    val = self._resolve_value(str(tokens[idx + 1]))
                    result = not val
                    tokens = tokens[:idx] + [result] + tokens[idx+2:]
                    continue
            
            for op in ['==', '!=', '>=', '<=', '>', '<']:
                if op in tokens:
                    idx = tokens.index(op)
                    if idx > 0 and idx < len(tokens) - 1:
                        left = self._resolve_value(str(tokens[idx - 1]))
                        right = self._resolve_value(str(tokens[idx + 1]))
                        result = self.operators[op](left, right)
                        tokens = tokens[:idx-1] + [result] + tokens[idx+2:]
                        break
            else:
                break
        
        while 'AND' in tokens or 'OR' in tokens:
            for op in ['AND', 'OR']:
                if op in tokens:
                    idx = tokens.index(op)
                    if idx > 0 and idx < len(tokens) - 1:
                        left = self._resolve_value(str(tokens[idx - 1]))
                        right = self._resolve_value(str(tokens[idx + 1]))
                        result = self.operators[op](left, right)
                        tokens = tokens[:idx-1] + [result] + tokens[idx+2:]
                        break
                else:
                    continue
                break
        
        if len(tokens) == 1:
            return self._resolve_value(str(tokens[0]))
        
        return None

    def evaluate(self, expression: str) -> Optional[bool]:
        """
        Evalúa una expresión lógica de forma segura.

        Args:
            expression: Expresión lógica a evaluar

        Returns:
            Resultado booleano o None si falla
        """
        try:
            tokens = self._tokenize(expression)
            result = self._evaluate_expression(tokens)
            
            if isinstance(result, bool):
                return result
            
            if result is None:
                return None
            
            return bool(result)
        except Exception as e:
            logger.warning(f"Error evaluando expresión '{expression}': {e}")
            return None

    def evaluate_severity(self, severity_logic: Dict[str, Optional[str]]) -> Optional[str]:
        """
        Evalúa la lógica de severidad y retorna el nivel asignado.

        Args:
            severity_logic: Diccionario con condiciones de severidad

        Returns:
            Nivel de severidad ('critical', 'high', 'medium', 'low') o None
        """
        order = ['critical', 'high', 'medium', 'low']
        
        for level in order:
            condition = severity_logic.get(level)
            if condition:
                result = self.evaluate(condition)
                if result is True:
                    return level
        
        return None

    def evaluate_confidence(self, confidence_logic: Dict[str, Optional[str]]) -> Optional[str]:
        """
        Evalúa la lógica de confianza y retorna el nivel asignado.

        Args:
            confidence_logic: Diccionario con condiciones de confianza

        Returns:
            Nivel de confianza ('high', 'medium', 'low', 'indeterminate') o None
        """
        order = ['high', 'medium', 'low', 'indeterminate']
        
        for level in order:
            condition = confidence_logic.get(level)
            if condition:
                result = self.evaluate(condition)
                if result is True:
                    return level
        
        return 'indeterminate'

    def format_template(self, template: str, variables: Dict[str, Any]) -> str:
        """
        Formatea un template reemplazando placeholders.

        Args:
            template: Template con placeholders {variable}
            variables: Diccionario de variables para sustituir

        Returns:
            Template formateado
        """
        result = template
        all_vars = {**self.variables, **variables}
        
        import re
        pattern = r'\{([^}]+)\}'
        
        def replace(match):
            var_name = match.group(1).strip()
            if var_name in all_vars:
                value = all_vars[var_name]
                return str(value) if value is not None else '[no disponible]'
            return match.group(0)
        
        result = re.sub(pattern, replace, result)
        
        return result

