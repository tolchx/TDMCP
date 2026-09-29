uint flatten3(ivec3 c, uint R){
    return uint(c.x) + R * (uint(c.y) + R * uint(c.z));
}

float sampleTemp_trilinear(vec3 x, vec3 bmin, vec3 h, uint R){
    // coordonnées de grille centrées (centres à i+0.5)
    vec3 g = (x - bmin) / h - vec3(0.5);

    ivec3 i0 = ivec3(floor(g));
    ivec3 i1 = i0 + ivec3(1);
    vec3  f  = clamp(fract(g), 0.0, 1.0);

    ivec3 lo = ivec3(0);
    ivec3 hi = ivec3(int(R) - 1);
    i0 = clamp(i0, lo, hi);
    i1 = clamp(i1, lo, hi);

    float c000 = TDIn_Temp(0, flatten3(ivec3(i0.x, i0.y, i0.z), R));
    float c100 = TDIn_Temp(0, flatten3(ivec3(i1.x, i0.y, i0.z), R));
    float c010 = TDIn_Temp(0, flatten3(ivec3(i0.x, i1.y, i0.z), R));
    float c110 = TDIn_Temp(0, flatten3(ivec3(i1.x, i1.y, i0.z), R));
    float c001 = TDIn_Temp(0, flatten3(ivec3(i0.x, i0.y, i1.z), R));
    float c101 = TDIn_Temp(0, flatten3(ivec3(i1.x, i0.y, i1.z), R));
    float c011 = TDIn_Temp(0, flatten3(ivec3(i0.x, i1.y, i1.z), R));
    float c111 = TDIn_Temp(0, flatten3(ivec3(i1.x, i1.y, i1.z), R));

    float c00 = mix(c000, c100, f.x);
    float c10 = mix(c010, c110, f.x);
    float c01 = mix(c001, c101, f.x);
    float c11 = mix(c011, c111, f.x);
    float c0  = mix(c00,  c10,  f.y);
    float c1  = mix(c01,  c11,  f.y);
    return mix(c0, c1, f.z);
}

void main(){
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;

    // métriques de grille
    uint R = max(SimRes, 1u);
    vec3 size = vec3(SimSizex, SimSizey, SimSizez);
    vec3 bmin = vec3(-0.5*size.x, -0.5*size.y, -0.5*size.z);
    vec3 bmax = -bmin;
    vec3 h    = size / float(R);

    // backtrace avec U
    vec3 pos = TDIn_P();
    vec3 u   = TDIn_U();
    vec3 x_back = clamp(pos - dt * u, bmin, bmax);

    // échantillonnage trili de Temp à x_back
    float t_adv = sampleTemp_trilinear(x_back, bmin, h, R);

    // sortie : on stocke aussi dans Temp_tmp (RHS pour la diffusion)
    Temp[id]     = t_adv;
    Temp_tmp[id] = t_adv;
}
