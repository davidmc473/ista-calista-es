# Spec 003 — Icono y logo de ista

| Campo   | Valor |
|---------|-------|
| Estado  | Implementada |
| Fecha   | 2026-11-08 |
| Depende | Spec 001 |

## 1. Contexto

Sin imágenes propias, Home Assistant y HACS muestran un icono genérico. Las integraciones de
HA usan el logo oficial de la marca. ista ya tiene sus imágenes en el repositorio de marcas
de Home Assistant (integración oficial `ista_ecotrend`, ista Alemania), y el logo es el mismo
para ista España.

## 2. Aceptación

1. La integración se muestra con el icono y el logo oficiales de ista en *Dispositivos y
   servicios*, también con el tema oscuro.
2. Las imágenes son las publicadas en `https://brands.home-assistant.io/ista_ecotrend/`, sin
   modificar.

## 3. Requisitos

| ID     | Requisito |
|--------|-----------|
| FR-301 | Carpeta `custom_components/ista_calista_es/brand/` con `icon.png` (256×256), `icon@2x.png` (512×512), `logo.png`, `logo@2x.png` y sus variantes `dark_*`, como el proyecto Livebox. |
| FR-302 | La validación de HACS sigue ignorando `brands` hasta que el dominio esté en `home-assistant/brands`. |
