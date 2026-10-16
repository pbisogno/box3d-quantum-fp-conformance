// PRIVATE compatibility laboratory. Do not publish with Box3D public sources.
// Independently expressed unsigned C arithmetic, constrained by public SDK API
// observations. Native C conformance has not yet been executed.
#ifndef QUANTUM_FP_C_PRIVATE_H
#define QUANTUM_FP_C_PRIVATE_H
#include <stdint.h>
#include <limits.h>
#include <string.h>
#include <stdlib.h>

typedef struct { uint64_t bits; } qfp;
typedef enum { QFP_OK=0,QFP_DIVIDE_BY_ZERO=1,QFP_OVERFLOW=2,QFP_DOMAIN=3,QFP_LUT_UNINITIALIZED=4,QFP_UNPROVEN=5,QFP_INDEX_OUT_OF_RANGE=6,QFP_LUT_INVALID=7 } qfp_status;
typedef struct { qfp value;qfp_status status; } qfp_result;
typedef struct { int32_t value;qfp_status status; } qfp_i32_result;
_Static_assert(sizeof(uint64_t)==8&&sizeof(int64_t)==8&&sizeof(int32_t)==4,"fixed width types");
_Static_assert(INT64_MIN==-INT64_MAX-1,"two complement int64 representation");
_Static_assert(sizeof(qfp)==8,"raw FP ABI");
#define QFP_INIT_RAW(x) { (uint64_t)(int64_t)(x) }
#define QFP_CONST_RAW(x) ((qfp){(uint64_t)(int64_t)(x)})
#define QFP_ZERO QFP_CONST_RAW(0)
#define QFP_ONE QFP_CONST_RAW(65536)
#define QFP_HALF QFP_CONST_RAW(32768)
#define QFP_PRECISION 16
#define QFP_MUL_ROUND UINT64_C(32768)
static inline qfp qfp_from_bits(uint64_t u) { return (qfp){u}; }
static inline uint64_t qfp_bits(qfp a) { return a.bits; }
static inline qfp qfp_from_raw(int64_t s) { uint64_t u;memcpy(&u,&s,8);return qfp_from_bits(u); }
static inline int64_t qfp_raw(qfp a) { int64_t s;memcpy(&s,&a.bits,8);return s; }
static inline uint64_t qfp_asr_bits(uint64_t u,unsigned n) { if(!n)return u;if(n>=64)return u>>63?UINT64_MAX:0;return (u>>n)|((u>>63)?(UINT64_MAX<<(64-n)):0); }
static inline qfp qfp_from_i32(int32_t a) { return qfp_from_bits(((uint64_t)(int64_t)a)<<16); }
static inline qfp qfp_add(qfp a,qfp b) { return qfp_from_bits(a.bits+b.bits); }
static inline qfp qfp_sub(qfp a,qfp b) { return qfp_from_bits(a.bits-b.bits); }
static inline qfp qfp_neg(qfp a) { return qfp_from_bits(UINT64_C(0)-a.bits); }
static inline qfp qfp_mul(qfp a,qfp b) { return qfp_from_bits(qfp_asr_bits(a.bits*b.bits+QFP_MUL_ROUND,16)); }
static inline int qfp_cmp(qfp a,qfp b) { uint64_t x=a.bits^UINT64_C(0x8000000000000000),y=b.bits^UINT64_C(0x8000000000000000);return (x>y)-(x<y); }
static inline int qfp_eq(qfp a,qfp b) { return a.bits==b.bits; }
static inline int qfp_lt(qfp a,qfp b) { return qfp_cmp(a,b)<0; }
static inline int qfp_le(qfp a,qfp b) { return qfp_cmp(a,b)<=0; }
static inline qfp qfp_sign(qfp a) { return a.bits>>63?QFP_CONST_RAW(-65536):QFP_ONE; }
static inline qfp qfp_min(qfp a,qfp b) { return qfp_lt(a,b)?a:b; }
static inline qfp qfp_max(qfp a,qfp b) { return qfp_lt(a,b)?b:a; }
static inline qfp qfp_abs(qfp a) { return a.bits>>63?qfp_neg(a):a; }
static inline qfp_result qfp_try_div(qfp a,qfp b) {
    uint64_t n=a.bits<<16,d=b.bits;
    if(!d)return (qfp_result){QFP_ZERO,QFP_DIVIDE_BY_ZERO};
    if(n==UINT64_C(0x8000000000000000)&&d==UINT64_MAX)return (qfp_result){QFP_ZERO,QFP_OVERFLOW};
    uint64_t nm=n>>63?UINT64_C(0)-n:n,dm=d>>63?UINT64_C(0)-d:d;
    uint64_t q=nm/dm;if((n^d)>>63)q=UINT64_C(0)-q;
    return (qfp_result){qfp_from_bits(q),QFP_OK};
}
static inline qfp_result qfp_try_mod(qfp a,qfp b) {
    uint64_t n=a.bits,d=b.bits;if(!d)return (qfp_result){QFP_ZERO,QFP_DIVIDE_BY_ZERO};
    if(n==UINT64_C(0x8000000000000000)&&d==UINT64_MAX)return (qfp_result){QFP_ZERO,QFP_OVERFLOW};
    uint64_t nm=n>>63?UINT64_C(0)-n:n,dm=d>>63?UINT64_C(0)-d:d;
    uint64_t r=nm%dm;if(n>>63)r=UINT64_C(0)-r;return (qfp_result){qfp_from_bits(r),QFP_OK};
}
// Checked convenience wrappers deliberately fail closed; they never saturate.
static inline qfp qfp_require(qfp_result r) { if(r.status!=QFP_OK)abort();return r.value; }
static inline qfp qfp_div(qfp a,qfp b) { return qfp_require(qfp_try_div(a,b)); }
static inline qfp qfp_mod(qfp a,qfp b) { return qfp_require(qfp_try_mod(a,b)); }
static inline qfp_result qfp_try_from_ratio(int32_t a,int32_t b) { return qfp_try_div(qfp_from_i32(a),qfp_from_i32(b)); }
static inline qfp qfp_from_ratio(int32_t a,int32_t b) { return qfp_require(qfp_try_from_ratio(a,b)); }
static inline qfp qfp_floor(qfp a) { return qfp_from_bits(a.bits&~UINT64_C(65535)); }
static inline qfp qfp_ceil(qfp a) { return qfp_from_bits((a.bits+UINT64_C(65535))&~UINT64_C(65535)); }
static inline qfp qfp_trunc(qfp a) { return a.bits>>63?qfp_neg(qfp_floor(qfp_neg(a))):qfp_floor(a); }
// SDK FPMath.Round observed tie-to-even; distinct from RoundToInt below.
static inline qfp qfp_round(qfp a) {
    uint64_t f=a.bits&65535u,base=a.bits&~UINT64_C(65535);
    if(f>32768u||(f==32768u&&((base>>16)&1u)))base+=UINT64_C(65536);
    return qfp_from_bits(base);
}
static inline int32_t qfp_i32_low(uint64_t x) { uint32_t u=(uint32_t)x;int32_t s;memcpy(&s,&u,4);return s; }
// SDK integral accessors / round-to-int wrap the final int32 conversion.
static inline int32_t qfp_as_i32(qfp a) { return qfp_i32_low(qfp_asr_bits(a.bits,16)); }
static inline int32_t qfp_floor_to_i32(qfp a) { return qfp_as_i32(a); }
static inline int32_t qfp_ceil_to_i32(qfp a) { return qfp_i32_low(qfp_asr_bits(a.bits+UINT64_C(65535),16)); }
static inline int32_t qfp_round_to_i32(qfp a) { return qfp_i32_low(qfp_asr_bits(a.bits+UINT64_C(32768),16)); }
// Explicit mathematical truncation+range checking, NOT the SDK AsInt accessor.
static inline qfp_i32_result qfp_try_to_i32_trunc(qfp a) {
    uint64_t mag=(a.bits>>63?UINT64_C(0)-a.bits:a.bits)>>16;
    if(mag>(a.bits>>63?UINT64_C(2147483648):UINT64_C(2147483647)))return (qfp_i32_result){0,QFP_OVERFLOW};
    if(a.bits>>63)mag=UINT64_C(0)-mag;return (qfp_i32_result){qfp_i32_low(mag),QFP_OK};
}
// Encoding-level validity only: individual function domains are checked separately.
static inline int qfp_is_valid(qfp a) { (void)a;return 1; }
// Read-only after initialization; load/free must happen outside concurrent use.
extern const uint32_t* qfp_sqrt_lut;
extern const uint64_t* qfp_sincos_lut;
extern const uint64_t* qfp_acos_lut;
extern const uint64_t* qfp_asin_lut;
extern const uint64_t* qfp_atan_lut;
qfp_status qfp_lut_init(const char* directory);
void qfp_lut_free(void);
static inline qfp_result qfp_try_sqrt(qfp a) {
    if(a.bits>>63)return (qfp_result){QFP_ZERO,QFP_DOMAIN};
    if(!qfp_sqrt_lut)return (qfp_result){QFP_ZERO,QFP_LUT_UNINITIALIZED};
    uint64_t index=a.bits;int shift=-6;while(index>65536u){index>>=2;++shift;}
    uint64_t value=qfp_sqrt_lut[index];value=shift>=0?value<<(unsigned)shift:value>>(unsigned)-shift;
    return (qfp_result){qfp_from_bits(value),QFP_OK};
}
static inline qfp_result qfp_try_rcp(qfp a) { return qfp_try_div(QFP_ONE,a); }
static inline qfp_result qfp_try_sin(qfp a) {
    if(!qfp_sincos_lut)return (qfp_result){QFP_ZERO,QFP_LUT_UNINITIALIZED};
    if(a.bits==UINT64_C(0x8000000000000000))return (qfp_result){QFP_ZERO,QFP_INDEX_OUT_OF_RANGE};
    uint64_t mag=a.bits>>63?UINT64_C(0)-a.bits:a.bits;int32_t value=qfp_i32_low(qfp_sincos_lut[mag%411775u]);
    qfp raw=qfp_from_raw((int64_t)value);if(a.bits>>63)raw=qfp_neg(raw);return (qfp_result){raw,QFP_OK};
}
static inline qfp_result qfp_try_cos(qfp a) {
    if(!qfp_sincos_lut)return (qfp_result){QFP_ZERO,QFP_LUT_UNINITIALIZED};
    if(a.bits==UINT64_C(0x8000000000000000))return (qfp_result){QFP_ZERO,QFP_INDEX_OUT_OF_RANGE};
    uint64_t mag=a.bits>>63?UINT64_C(0)-a.bits:a.bits;
    return (qfp_result){qfp_from_raw((int64_t)qfp_i32_low(qfp_sincos_lut[mag%411775u]>>32)),QFP_OK};
}
static inline qfp_result qfp_try_acos(qfp a) {
    if(qfp_lt(a,QFP_CONST_RAW(-65536))||qfp_lt(QFP_ONE,a))return (qfp_result){qfp_from_bits(UINT64_C(0x8000000000000000)),QFP_OK};
    if(!qfp_acos_lut)return (qfp_result){QFP_ZERO,QFP_LUT_UNINITIALIZED};
    return (qfp_result){qfp_from_bits(qfp_acos_lut[a.bits+65536u]),QFP_OK};
}
static inline qfp_result qfp_try_asin(qfp a) {
    if(qfp_lt(a,QFP_CONST_RAW(-65536))||qfp_lt(QFP_ONE,a))return (qfp_result){qfp_from_bits(UINT64_C(0x8000000000000000)),QFP_OK};
    if(!qfp_asin_lut)return (qfp_result){QFP_ZERO,QFP_LUT_UNINITIALIZED};
    return (qfp_result){qfp_from_bits(qfp_asin_lut[a.bits+65536u]),QFP_OK};
}
// Public API observations: segmented truncating index, not an interpolated libm atan.
static inline qfp_result qfp_try_atan(qfp a) {
    if(!qfp_atan_lut)return (qfp_result){QFP_ZERO,QFP_LUT_UNINITIALIZED};
    if(a.bits==UINT64_C(0x8000000000000000))return (qfp_result){QFP_ZERO,QFP_INDEX_OUT_OF_RANGE};
    uint64_t mag=a.bits>>63?UINT64_C(0)-a.bits:a.bits,index;
    if(mag<=UINT64_C(393216))index=mag;
    else if(mag<=UINT64_C(16384000))index=UINT64_C(393216)+((mag-UINT64_C(393216))>>12);
    else {index=UINT64_C(397120)+((mag-UINT64_C(16384000))>>20);if(index>397729u)index=397729u;}
    qfp value=qfp_from_bits(qfp_atan_lut[index]);if(a.bits>>63)value=qfp_neg(value);
    return (qfp_result){value,QFP_OK};
}
static inline qfp_result qfp_try_atan2(qfp y,qfp x) {
    if(!x.bits)return (qfp_result){!y.bits?QFP_ZERO:(y.bits>>63?QFP_CONST_RAW(-102944):QFP_CONST_RAW(102944)),QFP_OK};
    qfp_result ratio=qfp_try_div(y,x);if(ratio.status!=QFP_OK)return ratio;
    qfp_result angle=qfp_try_atan(ratio.value);if(angle.status!=QFP_OK)return angle;
    if(x.bits>>63)angle.value=qfp_add(angle.value,y.bits>>63?QFP_CONST_RAW(-205887):QFP_CONST_RAW(205887));
    return angle;
}
static inline qfp qfp_sqrt(qfp a) { return qfp_require(qfp_try_sqrt(a)); }
static inline qfp qfp_sin(qfp a) { return qfp_require(qfp_try_sin(a)); }
static inline qfp qfp_cos(qfp a) { return qfp_require(qfp_try_cos(a)); }
static inline qfp qfp_acos(qfp a) { return qfp_require(qfp_try_acos(a)); }
static inline qfp qfp_asin(qfp a) { return qfp_require(qfp_try_asin(a)); }
static inline qfp qfp_atan(qfp a) { return qfp_require(qfp_try_atan(a)); }
static inline qfp qfp_atan2(qfp y,qfp x) { return qfp_require(qfp_try_atan2(y,x)); }
#endif
