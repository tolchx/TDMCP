---
name: td-embody-tdxn
description: "Guía completa del formato TDXN v2.1 (TouchDesigner eXternal Network) y flujos de externalización para Git y agentes de IA. Generación masiva de redes en YAML, optimización de tokens y reconstrucción determinista."
---

# TDXN v2.1: Redes de TouchDesigner en YAML Diffable

**TDXN (TouchDesigner eXternal Network)** es el formato de serialización de texto plano en YAML creado por Dylan Roscover (Embody) para resolver el problema de los archivos binarios `.toe`/`.tox` en TouchDesigner. Permite a los agentes de IA leer, generar y modificar redes complejas en un solo turno, reduciendo drásticamente el consumo de tokens (entre 20x y 90x frente a llamadas RPC individuales) y habilitando control de versiones real con Git.

---

## 1. Anatomía del Formato TDXN v2.1

Un documento `.tdxn` representa un COMP o un proyecto completo.

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/dylanroscover/Embody/main/docs/tdxn.schema.yaml
format: tdxn
version: '2.0'
generator: Embody/6.2.69
td_build: '2025.33230'
network_path: /project1/synth
options:
  include_dat_content: true
  include_storage: false

# 1. Defaults por tipo: Evita repetir parámetros compartidos
type_defaults:
  baseCOMP:
    parameters:
      resizecomp: =me
      repocomp: =me

# 2. Plantillas de Parámetros: Estructuras reutilizables de Custom Parameters
par_templates:
  meta:
    - {name: Build, style: Int, label: Build Number, readOnly: true}
    - {name: Version, style: Str, label: Version, readOnly: true}

# 3. Operadores de la Red
operators:
  - name: osc1
    type: waveCHOP
    position: [0, 0]
    parameters:
      wavetype: sine
      freq: 2.0
      amp: 0.5
    flags: [viewer]

  - name: math1
    type: mathCHOP
    position: [200, 0]
    parameters:
      gain: 1.5
    inputs: [osc1]

  - name: out1
    type: nullCHOP
    position: [400, 0]
    inputs: [math1]
    flags: [display]

  - name: config
    type: tableDAT
    position: [0, -200]
    dat_content:
      - [param, value]
      - [samplerate, '44100']
    dat_content_format: table

  - name: logic_script
    type: textDAT
    position: [200, -200]
    dat_content: |
      def onCook(dat):
          # Logica interna del DAT
          pass
    dat_content_format: text

# 4. Anotaciones visuales en el canvas
annotations:
  - name: annot_synth
    mode: annotate
    title: Oscillator Core
    text: Generador de onda y amplificación
    position: [-50, -100]
    size: [550, 250]
```

---

## 2. Convenciones y Reglas de Valor en TDXN

1. **Expresiones con prefijo `=`:**
   - En TDXN no se usan objetos anidados de modo. Toda expresión Python comienza directamente con `=`:
     ```yaml
     opacity: =parent().par.Speed / 10
     ```
2. **Bindings con prefijo `~`:**
   - Todo enlace bidireccional se expresa con prefijo `~`:
     ```yaml
     cutoff: ~op('null_ctrl')['cutoff']
     ```
3. **Flags como Listas Compactas:**
   - Se declaran como una lista simple de strings con los flags activos:
     ```yaml
     flags: [display, render, viewer, lock]
     ```
4. **Conexiones de Entrada (`inputs`):**
   - Una lista donde el índice corresponde al conector de entrada (Input 0, Input 1, etc.):
     ```yaml
     inputs: [source_a, source_b]
     ```
   - Si una entrada intermedia no está conectada, se usa `null`:
     ```yaml
     inputs: [source_a, null, source_c]
     ```
5. **Contenido de DATs:**
   - **Texto / Código (Python/GLSL):** Usar el operador literal de bloque de YAML (`|`). Mantiene la indentación y permite que `git diff` muestre cambios línea a línea.
   - **Tablas:** Lista de listas de strings:
     ```yaml
     dat_content:
       - [col1, col2]
       - [val1, val2]
     ```

---

## 3. Economía de TDXN (Reglas de Optimización)

Al diseñar o generar redes para TDXN:

- **Usar Clones en lugar de Redes Duplicadas:**
  Si varios COMPs comparten la misma lógica interna, uno actúa como master (`clone`) y los hermanos solo almacenan sus valores de parámetros custom. TDXN solo exportará los valores, no los hijos.
- **`parameterCHOP` sobre `constantCHOP` con expresiones:**
  Un solo `parameterCHOP` configurado con `ops='..'` emite todos los parámetros custom en 3 líneas de TDXN y cocina solo cuando un parámetro cambia. Evita crear decenas de bloques `value: =parent().par.X`.
- **Compartir DATs para Shaders Idénticos:**
  Si múltiples `glslTOP` ejecutan el mismo shader diferenciándose solo por uniforms, haz que apunten al mismo DAT en lugar de duplicar el código del shader.
- **Confiar en los Defaults:**
  TDXN exporta únicamente valores que difieran del valor por defecto del operador o del `type_defaults`. No fuerces valores que ya son el default.

---

## 4. Flujo de Trabajo para Agentes de IA

1. **Lectura Eficiente:**
   - En lugar de inspeccionar nodo por nodo con múltiples llamadas RPC, lee el `.tdxn` del COMP o ejecuta la herramienta de exportación/lectura.
2. **Edición o Generación:**
   - Para crear una red completa de 10-20 nodos, redacta el bloque TDXN YAML completo y envíalo mediante `td_import_tdn` / `import_network` con `clear_first=true`.
3. **Verificación Inmediata:**
   - Verifica que no existan errores de cocinado (`td_get_errors`).
   - Verifica que el render final no esté en negro (`capture_top`).
