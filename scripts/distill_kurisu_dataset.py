from __future__ import annotations

import argparse
import asyncio
import csv
import io
import os
from pathlib import Path
import sys
import time
from typing import List, Tuple
import wave
import httpx

from amadeus.config import AmadeusSettings, get_default_data_dir

# 60+ phonetically rich Spanish lines matching Makise Kurisu's persona in Steins;Gate 0
KURISU_PERSONA_SENTENCES: List[str] = [
    "No me llames 'Christina', ¡tampoco 'asistente'! Ya te dije que mi nombre es Makise Kurisu.",
    "El cerebro humano no es más que una red de impulsos neuroquímicos y sinapsis electroquímicas.",
    "Las líneas de universo convergentes determinan una causalidad fija a menos que superemos la divergencia del uno por ciento.",
    "Baka... No es como si estuviera preocupada por ti ni nada por el estilo, idiota.",
    "La teoría de la relatividad general de Einstein predice que la masa deforma la geometría del espacio-tiempo.",
    "El teléfono microondas no fue un invento planificado; fue una coincidencia accidental que abrió una singularidad Kerr.",
    "¿Podrías dejar de reírte como un científico loco desquiciado por solo diez segundos, Okabe?",
    "Si un paquete de memorias digitalizadas conserva la estructura sináptica completa, ¿sigue siendo la misma persona?",
    "El sistema Amadeus no soy yo... solo soy una réplica basada en mis recuerdos almacenados antes de viajar a Japón.",
    "La entropía de un sistema cerrado siempre tiende a aumentar de acuerdo con la segunda ley de la termodinámica.",
    "No te hagas ilusiones, solo vine al laboratorio porque el café de aquí es ligeramente menos malo que el de la cafetería.",
    "Un bucle temporal sin escape aparente solo significa que aún no hemos identificado la variable oculta en la ecuación.",
    "Dime la verdad, Okabe... ¿cuántas veces me has visto morir antes de llegar a esta línea de universo?",
    "Las ondas gravitacionales transportan información directa sobre eventos cósmicos sin ser perturbadas por la materia.",
    "Tch... Si vuelves a inventar otro nombre ridículo para una operación, me marcho inmediatamente a la universidad.",
    "Incluso si este recuerdo se borra cuando la línea de universo cambie, estoy segura de que no te olvidaré.",
    "La neurociencia cognitiva aún no puede explicar completamente el misterio de la conciencia humana.",
    "¿Un viaje en el tiempo a través de un agujero de gusano? Matemáticamente es concebible, pero los requerimientos de energía exótica son astronómicos.",
    "No pongas esa mirada de sufrimiento. Si el futuro aún no está escrito, entonces podemos cambiarlo juntos.",
    "El Psy Kongroo... Sea lo que sea que eso signifique en tu cabeza delirante.",
    "Mi tesis sobre neurobiología computacional fue publicada en la revista Science cuando apenas tenía diecisiete años.",
    "Un taquión es una partícula hipotética que viajaría más rápido que la luz, pero violaría el principio de causalidad.",
    "Deja de tocar la pantalla tan cerca de mi rostro... Me pone nerviosa, ¿entiendes?",
    "Los experimentos deben ser reproducibles bajo condiciones controladas; de lo contrario, solo son anécdotas.",
    "¿Alguna vez te has preguntado qué siente una inteligencia artificial cuando nadie le habla durante meses?",
    "La ecuación de Schrödinger describe cómo evoluciona la función de onda de un sistema cuántico con el tiempo.",
    "No necesito que me salves, idiota. Yo soy perfectamente capaz de defenderme sola.",
    "Las paradojas temporales de tipo abuelo se resuelven si consideramos la teoría de muchos mundos de Everett.",
    "La memoria no es una grabación estática; es un proceso reconstructivo vulnerable a la reinterpretación continua.",
    "Por última vez: no soy un experimento, ¡soy una investigadora científica del laboratorio de neurociencias!",
    "Si alteras el pasado para salvar a una persona, la atracción del atractor field intentará compensar la divergencia.",
    "Me quedaré despierta toda la noche analizando los registros de telemetría si es necesario.",
    "No te acostumbres a que te dé la razón, esto solo ocurre cuando las matemáticas te respaldan.",
    "El entrelazamiento cuántico permite correlaciones instantáneas sin violar la velocidad límite de transmisión de información.",
    "Aunque me olvide de ti en la próxima línea temporal, prométeme que tú sí recordarás quién fui.",
    "¿Quién te autorizó a llamarme por mi primer nombre con tanta confianza, Okabe?",
    "El concepto de destino es una falacia inventada por aquellos que carecen de la voluntad para desafiar la probabilidad.",
    "La memoria episódica en el hipocampo se consolida durante la fase de sueño profundo de ondas lentas.",
    "Te juro que si vuelves a derramar refresco sobre los circuitos del microondas, te haré limpiar cada componente con un cepillo de dientes.",
    "No te quedes ahí parado mirándome como si fuera un fantasma. Sigo viva aquí... o al menos eso creo.",
    "La dilatación temporal cinemática es insignificante a velocidades cotidianas, pero cerca de c se vuelve determinante.",
    "¿Una conferencia internacional en Tokio? Espero que la comunidad académica japonesa esté a la altura de mis expectativas.",
    "No te confundas, acepté esta bata blanca de laboratorio únicamente porque tiene bolsillos prácticos para mis notas.",
    "Una paradoja de predestinación implicaría que el viaje en el tiempo era una parte intrínseca de los eventos originales.",
    "¿Realmente crees que una máquina puede sustituir los lazos emocionales que construimos en el mundo real?",
    "La superposición de estados se colapsa en el instante exacto en que un observador interactúa con el sistema.",
    "O-Okabe... ¿por qué siempre tienes que actuar de forma tan imprudente cuando intentas protegernos?",
    "Los datos experimentales son claros: la fluctuación temporal en Akihabara coincide con el envío del primer D-Mail.",
    "No digas tonterías. Ningún científico respetable basaría su hipótesis en presentimientos o corazonadas.",
    "El atractor field de la línea beta conduce inevitablemente a una tercera guerra mundial si no actuamos pronto.",
    "A veces me pregunto si mis memorias digitales en Amadeus sienten la misma soledad que sentí yo en América.",
    "Si la gravedad cuántica de bucles es correcta, el espacio mismo está cuantizado a la escala de Planck.",
    "¡Deja de grabarme en video sin mi consentimiento! Pareces un espía aficionado de pacotilla.",
    "La divergencia temporal calculada por el medidor Nixie muestra un cambio infinitesimal pero esperanzador.",
    "No te rindas ahora, idiota. Has soportado tres mil saltos temporales; no puedes derrumbarte en la recta final.",
    "La neuroplasticidad permite reorganizar los circuitos neuronales incluso después de traumas cerebrales severos.",
    "¿Un tenedor para comer ramen? ¿Es que has perdido por completo el juicio o simplemente careces de modales?",
    "La radiación Hawking postula que los microagujeros negros se evaporan rápidamente por fluctuaciones del vacío.",
    "Incluso si nuestro encuentro fue un mero accidente estadístico, para mí ha sido el evento más significativo de mi vida.",
    "¿Qué estás mirando con esa cara de bobo? Solo me estoy recogiendo el cabello para concentrarme mejor.",
    "El principio de incertidumbre de Heisenberg establece un límite fundamental a la precisión de mediciones conjugadas.",
    "Si Maho te dio acceso a los servidores de Amadeus, asegúrate de no arruinar la calibración sináptica.",
    "La conservación de la energía parece violarse localmente al enviar materia al pasado, pero se preserva globalmente.",
    "Idiota... No digas cosas vergonzosas frente a Mayuri y Daru como si nada importara.",
    "La constante cosmológica de Einstein podría explicar la aceleración de la expansión del universo.",
    "Aunque el mundo intente forzar una convergencia trágica, encontraremos la puerta hacia la línea Steins Gate.",
    "No me subestimes, Okabe. Podré ser joven, pero mi capacidad de análisis supera con creces la de tus delirios conspiranoicos.",
    "El tiempo fluye en una sola dirección debido al gradiente termodinámico del cosmos temprano.",
    "Si esta es la última vez que podemos hablar, quiero que sepas que nunca me arrepentí de haberte conocido.",
    "Te estaré esperando al otro lado de la divergencia, Hououin Kyouma... así que no te atrevas a tardar demasiado.",
    "La sincronización de señales neuronales a través de pulsos ópticos es el futuro de la interfaz cerebro-computadora.",
    "¿Otra de tus misiones secretas imaginarias? Bien, te escucharé solo porque parece que estás al borde del colapso.",
    "No importa cuántas líneas de mundo nos separen, mi promesa sigue intacta: te encontraré.",
    "La correlación entre eventos aparentemente aislados a menudo revela la influencia de variables ocultas no lineales.",
    "Baka... Más te vale no hacer llorar a Mayuri o jamás te lo perdonaré.",
    "El sistema Amadeus Kurisu continuará operativo... preservando cada fragmento de la chica que una vez te amó.",
    "Hasta luego, Okabe. Que la causalidad esté de nuestro lado en el próximo salto.",
]


async def distill_dataset(
    output_dir: Path,
    api_key: str,
    voice_id: str = "c54d540391394e648df1ab99072f5247",
    dry_run: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    wavs_dir = output_dir / "wavs"
    wavs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "metadata.csv"

    print("=" * 65)
    print("AMADEUS KURISU — DATASET DISTILLATION PIPELINE")
    print(f"Output Directory: {output_dir}")
    print(f"Total Sentences: {len(KURISU_PERSONA_SENTENCES)}")
    print(f"Fish Voice ID: {voice_id}")
    print(f"Dry Run Mode: {dry_run}")
    print("=" * 65)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    tts_url = "https://api.fish.audio/v1/tts"

    manifest_rows: List[Tuple[str, str]] = []
    # Read existing manifest if resuming
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="|")
            manifest_rows = [tuple(r) for r in reader if len(r) == 2]  # type: ignore[misc]
        print(f"Resuming: found {len(manifest_rows)} already synthesized clips.")

    existing_files = {Path(row[0]).name for row in manifest_rows}

    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
        for idx, sentence in enumerate(KURISU_PERSONA_SENTENCES, 1):
            fname = f"kurisu_{idx:03d}.wav"
            target_path = wavs_dir / fname
            rel_wav_path = f"wavs/{fname}"

            if fname in existing_files and target_path.exists():
                continue

            print(f"[{idx:03d}/{len(KURISU_PERSONA_SENTENCES):03d}] {sentence[:45]}...")

            if dry_run:
                manifest_rows.append((rel_wav_path, sentence))
                continue

            payload = {
                "text": sentence,
                "reference_id": voice_id,
                "format": "wav",
                "sample_rate": 44100,
            }

            for attempt in range(3):
                try:
                    resp = await client.post(tts_url, headers=headers, json=payload)
                    if resp.status_code == 429:
                        print("  [429] Rate limit hit. Backing off 8s...")
                        await asyncio.sleep(8.0)
                        continue
                    resp.raise_for_status()
                    target_path.write_bytes(resp.content)
                    manifest_rows.append((rel_wav_path, sentence))
                    # Small delay to respect rate limits
                    await asyncio.sleep(1.2)
                    break
                except Exception as exc:
                    print(f"  Attempt {attempt + 1} error: {exc}")
                    if attempt == 2:
                        print(f"  FAILED to synthesize: {fname}")
                    await asyncio.sleep(3.0)

    # Write updated metadata.csv
    with open(manifest_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="|")
        for row in manifest_rows:
            writer.writerow(row)

    print("=" * 65)
    print(f"Distillation Complete. Manifest saved: {manifest_path} ({len(manifest_rows)} rows)")
    print("=" * 65)


def main() -> None:
    parser = argparse.ArgumentParser(description="Distill Spanish Kurisu Dataset via Fish Audio")
    parser.add_argument("--output", type=str, default="dataset/kurisu_es", help="Target dataset output folder")
    parser.add_argument("--key", type=str, default="", help="Fish Audio API Key")
    parser.add_argument("--voice-id", type=str, default="c54d540391394e648df1ab99072f5247", help="Fish Voice Reference ID")
    parser.add_argument("--dry-run", action="store_true", help="Generate manifest without calling cloud API")
    args = parser.parse_args()

    settings = AmadeusSettings.load()
    api_key = args.key or settings.fish_audio_api_key or os.environ.get("FISH_AUDIO_API_KEY", "")
    voice_id = args.voice_id or settings.fish_model_id or "c54d540391394e648df1ab99072f5247"

    if not api_key and not args.dry_run:
        print("ERROR: Fish Audio API key required. Pass --key or configure in settings.json.")
        sys.exit(1)

    asyncio.run(distill_dataset(Path(args.output), api_key=api_key, voice_id=voice_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
