// PRIVATE: prepared for approved native execution; never run in public CI.
#include "fp.h"
#include <inttypes.h>
#include <stdio.h>

static int parse_bits(const char* s,uint64_t* out) {
    if(strlen(s)!=16)return 0;uint64_t v=0;
    for(int i=0;i<16;++i){unsigned char c=(unsigned char)s[i];int n=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;if(n<0)return 0;v=(v<<4)|(unsigned)n;}*out=v;return 1;
}
static int arithmetic_selftest(void) {
    return qfp_bits(qfp_mul(qfp_from_raw(-1),QFP_HALF))==0&&qfp_eq(qfp_round(QFP_CONST_RAW(-32768)),QFP_ZERO)&&qfp_round_to_i32(QFP_HALF)==1&&qfp_as_i32(qfp_from_raw(-1))==-1&&qfp_try_div(QFP_ONE,QFP_ZERO).status==QFP_DIVIDE_BY_ZERO&&qfp_bits(qfp_div(QFP_ONE,qfp_from_i32(2)))==32768;
}
int main(int argc,char** argv) {
    const char* inpath=NULL,*outpath=NULL,*lut=NULL;
    for(int i=1;i+1<argc;i+=2){if(!strcmp(argv[i],"--input"))inpath=argv[i+1];else if(!strcmp(argv[i],"--output"))outpath=argv[i+1];else if(!strcmp(argv[i],"--lut-dir"))lut=argv[i+1];else return 64;}
    if(argc%2==0||!arithmetic_selftest())return 64;
    if(lut&&qfp_lut_init(lut)!=QFP_OK)return 5;
    FILE* in=inpath?fopen(inpath,"rb"):stdin;FILE* out=outpath?fopen(outpath,"wb"):stdout;
    if(!in||!out){if(in&&in!=stdin)fclose(in);if(out&&out!=stdout)fclose(out);qfp_lut_free();return 5;}
    fprintf(out,"{\"schema\":\"private-qfp-c-v1\",\"type\":\"provenance\",\"arithmetic_selftest\":true,\"lut_loaded\":%s,\"precision\":16,\"mul_round\":32768}\n",lut?"true":"false");
    char line[256],op[64],sa[18],sb[18],extra[2];uint64_t count=0,exceptions=0,unproven=0;int io=1;
    while(fgets(line,sizeof(line),in)){
        uint64_t ua,ub;if(!strchr(line,'\n')&&!feof(in)){io=0;break;}
        if(sscanf(line,"%63s %17s %17s %1s",op,sa,sb,extra)!=3||!parse_bits(sa,&ua)||!parse_bits(sb,&ub)){io=0;break;}
        qfp a=qfp_from_bits(ua),b=qfp_from_bits(ub);qfp_result r={QFP_ZERO,QFP_OK};int kind=0;int32_t vi=0;int64_t vl=0;int vb=0;
        if(!strcmp(op,"op_Addition"))r.value=qfp_add(a,b);
        else if(!strcmp(op,"op_Subtraction"))r.value=qfp_sub(a,b);
        else if(!strcmp(op,"op_Multiply"))r.value=qfp_mul(a,b);
        else if(!strcmp(op,"op_Division"))r=qfp_try_div(a,b);
        else if(!strcmp(op,"op_Modulus"))r=qfp_try_mod(a,b);
        else if(!strcmp(op,"op_UnaryNegation"))r.value=qfp_neg(a);
        else if(!strcmp(op,"op_UnaryPlus")||!strcmp(op,"FromRaw"))r.value=a;
        else if(!strcmp(op,"FromInt32"))r.value=qfp_from_i32(qfp_i32_low(ua));
        else if(!strcmp(op,"Abs"))r.value=qfp_abs(a);
        else if(!strcmp(op,"Floor"))r.value=qfp_floor(a);
        else if(!strcmp(op,"Ceiling"))r.value=qfp_ceil(a);
        else if(!strcmp(op,"Round"))r.value=qfp_round(a);
        else if(!strcmp(op,"FloorToInt")||!strcmp(op,"get_AsInt")){kind=1;vi=qfp_as_i32(a);}
        else if(!strcmp(op,"CeilToInt")){kind=1;vi=qfp_ceil_to_i32(a);}
        else if(!strcmp(op,"RoundToInt")){kind=1;vi=qfp_round_to_i32(a);}
        else if(!strcmp(op,"get_AsLong")){kind=2;vl=qfp_raw(qfp_from_bits(qfp_asr_bits(a.bits,16)));}
        else if(!strcmp(op,"op_LessThan")){kind=3;vb=qfp_lt(a,b);}
        else if(!strcmp(op,"op_GreaterThan")){kind=3;vb=qfp_lt(b,a);}
        else if(!strcmp(op,"op_Equality")){kind=3;vb=qfp_eq(a,b);}
        else if(!strcmp(op,"op_LessThanOrEqual")){kind=3;vb=qfp_le(a,b);}
        else if(!strcmp(op,"op_GreaterThanOrEqual")){kind=3;vb=qfp_le(b,a);}
        else if(!strcmp(op,"op_Inequality")){kind=3;vb=!qfp_eq(a,b);}
        else if(!strcmp(op,"Min"))r.value=qfp_min(a,b);
        else if(!strcmp(op,"Max"))r.value=qfp_max(a,b);
        else if(!strcmp(op,"Sign"))r.value=qfp_sign(a);
        else if(!strcmp(op,"Sqrt"))r=qfp_try_sqrt(a);
        else if(!strcmp(op,"Sin"))r=qfp_try_sin(a);
        else if(!strcmp(op,"Cos"))r=qfp_try_cos(a);
        else if(!strcmp(op,"Acos"))r=qfp_try_acos(a);
        else if(!strcmp(op,"Asin"))r=qfp_try_asin(a);
        else if(!strcmp(op,"Atan"))r=qfp_try_atan(a);
        else if(!strcmp(op,"Atan2"))r=qfp_try_atan2(a,b);
        else{io=0;break;}
        fprintf(out,"{\"type\":\"result\",\"index\":%" PRIu64 ",\"op\":\"%s\",\"a_bits\":\"%016" PRIx64 "\",\"b_bits\":\"%016" PRIx64 "\",\"status\":%d,",count,op,ua,ub,(int)r.status);
        if(kind==1)fprintf(out,"\"result_type\":\"Int32\",\"value\":\"%" PRId32 "\"",vi);
        else if(kind==2)fprintf(out,"\"result_type\":\"Int64\",\"value\":\"%" PRId64 "\"",vl);
        else if(kind==3)fprintf(out,"\"result_type\":\"Boolean\",\"value\":%s",vb?"true":"false");
        else fprintf(out,"\"result_type\":\"FP\",\"bits\":\"%016" PRIx64 "\"",qfp_bits(r.value));
        fputs("}\n",out);++count;exceptions+=r.status!=QFP_OK;unproven+=r.status==QFP_UNPROVEN;
    }
    io=io&&!ferror(in)&&!ferror(out)&&count>0;
    fprintf(out,"{\"schema\":\"private-qfp-c-v1\",\"type\":\"summary\",\"requests\":%" PRIu64 ",\"nonzero_status_results\":%" PRIu64 ",\"unproven\":%" PRIu64 ",\"io_pass\":%s}\n",count,exceptions,unproven,io?"true":"false");
    if(in!=stdin&&fclose(in))io=0;if(out!=stdout&&fclose(out))io=0;qfp_lut_free();return io&&!unproven?0:5;
}
