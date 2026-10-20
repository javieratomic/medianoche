# Avisos de terceros

La licencia propietaria de MEDIANOCHE no sustituye ni restringe las licencias de los componentes siguientes. Los textos originales y sus avisos de copyright deben acompañar a los componentes distribuidos. Este resumen no sustituye esos textos.

## LÖVE 11.5 y dependencias del runtime

MEDIANOCHE utiliza [LÖVE](https://love2d.org/), desarrollado por LOVE Development Team, bajo licencia **zlib**. Los paquetes de Windows y Linux incluyen el runtime; sus dependencias tienen licencias propias, no necesariamente zlib.

El archivo completo `license.txt` del runtime se conserva en la distribución como [licenses/LOVE-license.txt](licenses/LOVE-license.txt), junto con los demás avisos que acompañen a sus binarios. La relación y los términos de referencia están en el [archivo oficial de LÖVE 11.5](https://github.com/love2d/love/blob/11.5/license.txt); prevalecen los textos correspondientes al runtime efectivamente incluido.

Las bibliotecas mantienen sus licencias originales. Sus fuentes y recetas de compilación se distribuyen en `THIRD-PARTY-SOURCES-0.1.0.tar.gz`, junto a los paquetes del juego en la [misma release](https://github.com/javieratomic/medianoche/releases/tag/v0.1.0). Consulta el [inventario de fuentes del motor](licenses/RUNTIME-SOURCES.md). El paquete Linux incluye además el texto original de su runtime como `licenses/LOVE-Linux-license.txt`.

## Libre Baskerville

Fuente **Libre Baskerville**, utilizada sin modificaciones; solo se ha simplificado el nombre del archivo a `LibreBaskerville.ttf`.

Copyright 2012 The Libre Baskerville Project Authors, con nombre reservado **Libre Baskerville**. Licencia **SIL Open Font License 1.1 (OFL)**.

- [Proyecto original](https://github.com/impallari/Libre-Baskerville).
- [Distribución de la fuente en Google Fonts](https://github.com/google/fonts/tree/main/ofl/librebaskerville).
- [Texto íntegro y aviso original en la distribución](licenses/LibreBaskerville-OFL.txt). También se conserva `OFL.txt` junto a la fuente en `assets/fonts/libre-baskerville/` dentro del juego.

Los permisos de uso, modificación y redistribución de la fuente son los de la OFL, no los de la licencia de MEDIANOCHE.

## vdf, componente del instalador de SteamOS

El instalador incluye **vdf (ValvePython/vdf)**, de Rossen Georgiev, bajo licencia **MIT**. Se utiliza para trabajar con los archivos KeyValues de Steam; no forma parte de la lógica del juego.

- [Proyecto](https://github.com/ValvePython/vdf).
- [Licencia original](https://github.com/ValvePython/vdf/blob/master/LICENSE).
- [Texto MIT íntegro y aviso de copyright en la distribución](licenses/vdf-LICENSE.txt), conservados también junto al componente del instalador.

Esta licencia se aplica a vdf, no automáticamente al juego ni al resto del instalador.

## Bibliotecas no incluidas

`lib/VENDOR.md` es una lista de propuestas de desarrollo, no un inventario de dependencias distribuidas. No hay implementaciones de esas bibliotecas en `lib/` en la revisión utilizada para preparar estos avisos; no se les atribuye uso por aparecer en esa lista.

Steam y SteamOS son marcas de sus respectivos titulares. La integración como juego externo no implica afiliación ni respaldo.
