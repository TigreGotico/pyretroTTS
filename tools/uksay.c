/* Minimal DECtalk multilang harness: force a language, render one utterance to
 * a WAV file. Bypasses say.c's MultiLang usage() guard so the non-US language
 * libraries (libtts_uk.so, ...) can be driven for capture. FONIX-derived API. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ttsapi.h"

LPTTS_HANDLE_T h;

int main(int argc, char *argv[]) {
    /* argv: <lang> <speaker> <outfile> <text> */
    if (argc < 5) { fprintf(stderr, "usage: uksay lang spk out.wav text\n"); return 2; }
    const char *lang = argv[1];
    int spk = atoi(argv[2]);
    char *out = argv[3];
    char *text = argv[4];

    unsigned int tl = TextToSpeechStartLang((char *)lang);
    if (tl & TTS_LANG_ERROR) { fprintf(stderr, "StartLang(%s) err %x\n", lang, tl); return 1; }
    TextToSpeechSelectLang(NULL, tl);

    MMRESULT st = TextToSpeechStartup(&h, 0, 0, NULL, (long)NULL);
    if (st != MMSYSERR_NOERROR) { fprintf(stderr, "Startup fail %d\n", st); return 1; }

    TextToSpeechSetSpeaker(h, spk);
    const char *logf = getenv("DECTALK_LOG_PHONEMES");
    if (logf) TextToSpeechOpenLogFile(h, (char *)logf, LOG_PHONEMES);
    if (TextToSpeechOpenWaveOutFile(h, out, WAVE_FORMAT_1M16) != MMSYSERR_NOERROR) {
        fprintf(stderr, "OpenWaveOutFile fail\n"); return 1; }
    TextToSpeechSpeak(h, text, TTS_FORCE);
    TextToSpeechSync(h);
    TextToSpeechCloseWaveOutFile(h);
    TextToSpeechShutdown(h);
    return 0;
}
