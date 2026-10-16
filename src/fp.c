// PRIVATE compatibility laboratory. LUT assets remain external, read-only SDK files.
#include "fp.h"
#include "sha256.h"
#include <stdio.h>

const uint32_t* qfp_sqrt_lut=NULL;
const uint64_t* qfp_sincos_lut=NULL;
const uint64_t* qfp_acos_lut=NULL;
const uint64_t* qfp_asin_lut=NULL;
const uint64_t* qfp_atan_lut=NULL;
static uint64_t load_le(const uint8_t* p,int width) { uint64_t v=0;for(int i=0;i<width;++i)v|=(uint64_t)p[i]<<(8*i);return v; }
static void* load_table(const char* dir,const char* file,size_t count,int width,const char* expected) {
    char path[2048];int written=snprintf(path,sizeof(path),"%s/%s",dir,file);if(written<0||(size_t)written>=sizeof(path))return NULL;
    FILE* f=fopen(path,"rb");if(!f)return NULL;size_t size=count*(size_t)width;uint8_t* raw=(uint8_t*)malloc(size);void* table=NULL;
    if(raw&&fread(raw,1,size,f)==size&&fgetc(f)==EOF){uint8_t hash[32];char hex[65];sk_sha256(raw,size,hash);sk_sha256_hex(hash,hex);
        if(!strcmp(hex,expected)){table=malloc(size);if(table)for(size_t i=0;i<count;++i){uint64_t value=load_le(raw+i*(size_t)width,width);if(width==4)((uint32_t*)table)[i]=(uint32_t)value;else((uint64_t*)table)[i]=value;}}
    }free(raw);fclose(f);return table;
}
void qfp_lut_free(void) { free((void*)qfp_sqrt_lut);free((void*)qfp_sincos_lut);free((void*)qfp_acos_lut);free((void*)qfp_asin_lut);free((void*)qfp_atan_lut);qfp_sqrt_lut=NULL;qfp_sincos_lut=NULL;qfp_acos_lut=NULL;qfp_asin_lut=NULL;qfp_atan_lut=NULL; }
qfp_status qfp_lut_init(const char* directory) {
    if(!directory||!sk_sha256_selftest())return QFP_LUT_INVALID;
    uint32_t* sqrt=(uint32_t*)load_table(directory,"FPSqrt.bytes",65537,4,"de5265f651730f20b54cc24bdcd3047e61320be44a5ae54796d290a189f4bca5");
    uint64_t* sc=(uint64_t*)load_table(directory,"FPSinCos.bytes",411775,8,"5c1659881bfcf3d7d2bde44c7b6757eba3152745eee26857ef4c4bd96e19b8a9");
    uint64_t* acos=(uint64_t*)load_table(directory,"FPAcos.bytes",131073,8,"2c3505e54884c950933608506296d99aad99f26488dbf444e2b85b0070784611");
    uint64_t* asin=(uint64_t*)load_table(directory,"FPAsin.bytes",131073,8,"33dba0d95450d20cfb8dea4d92f1b4940b1867a74e873f4484a42ab0b915f61c");
    uint64_t* atan=(uint64_t*)load_table(directory,"FPAtan.bytes",397730,8,"92cbe82f93380c8c0513c1ea7d070fd05cbfc50724aed2658acad9542f2689ec");
    if(!sqrt||!sc||!acos||!asin||!atan){free(sqrt);free(sc);free(acos);free(asin);free(atan);return QFP_LUT_INVALID;}
    qfp_lut_free();qfp_sqrt_lut=sqrt;qfp_sincos_lut=sc;qfp_acos_lut=acos;qfp_asin_lut=asin;qfp_atan_lut=atan;return QFP_OK;
}
