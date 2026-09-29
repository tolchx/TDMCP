// Diffusion_Temp_Aniso.glsl
uint flatten3(ivec3 c, uint R){
    return uint(c.x) + R * (uint(c.y) + R * uint(c.z));
}

void main(){
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;

    uint R = max(SimRes, 1u);
    vec3 size = vec3(SimSizex, SimSizey, SimSizez);
    vec3 h    = size / float(R);
    vec3 invh2 = 1.0 / (h * h);

    // indices
    uint i =  id              % R;
    uint j = (id / R)         % R;
    uint k =  id / (R*R);
    ivec3 I  = ivec3(int(i), int(j), int(k));
    ivec3 lo = ivec3(0), hi = ivec3(int(R)-1);

    // pas de diffusion → passthrough
    if (tempDiff <= 0.0){
        Temp[id]     = TDIn_Temp();
        Temp_tmp[id] = TDIn_Temp_tmp();
        return;
    }

    // BC Temp : Neumann (copie voisin intérieur)
    if (TDIn_Flag() == 1u){
        vec3  bnd = TDIn_BndN();
        ivec3 off = -ivec3(int(bnd.x), int(bnd.y), int(bnd.z));
        ivec3 Ii  = clamp(I + off, lo, hi);
        float t_in = TDIn_Temp(0, flatten3(Ii, R));
        Temp[id]     = t_in;
        Temp_tmp[id] = TDIn_Temp_tmp();
        return;
    }

    // voisins
    ivec3 L = clamp(I + ivec3(-1, 0, 0), lo, hi);
    ivec3 Rr= clamp(I + ivec3( 1, 0, 0), lo, hi);
    ivec3 D = clamp(I + ivec3( 0,-1, 0), lo, hi);
    ivec3 Uu= clamp(I + ivec3( 0, 1, 0), lo, hi);
    ivec3 B = clamp(I + ivec3( 0, 0,-1), lo, hi);
    ivec3 F = clamp(I + ivec3( 0, 0, 1), lo, hi);

    float tL = TDIn_Temp(0, flatten3(L,  R));
    float tR = TDIn_Temp(0, flatten3(Rr, R));
    float tD = TDIn_Temp(0, flatten3(D,  R));
    float tU = TDIn_Temp(0, flatten3(Uu, R));
    float tB = TDIn_Temp(0, flatten3(B,  R));
    float tF = TDIn_Temp(0, flatten3(F,  R));

    // RHS = Temp advectée (fixe pendant les passes)
    float tStar = TDIn_Temp_tmp();

    // (I - κ dt ∇²) T = T*
    float weightedSum = (tL + tR) * invh2.x
                      + (tD + tU) * invh2.y
                      + (tB + tF) * invh2.z;

    float denom = 1.0 + tempDiff * dt * 2.0 * (invh2.x + invh2.y + invh2.z);
    float tNext = (tStar + tempDiff * dt * weightedSum) / denom;

    Temp[id]     = tNext;
    Temp_tmp[id] = tStar;
}
