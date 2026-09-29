// Diffusion_U_Aniso.glsl
uint flatten3(ivec3 c, uint R){
    return uint(c.x) + R * (uint(c.y) + R * uint(c.z));
}

void main(){
    const uint id = TDIndex();
    if (id >= TDNumElements()) return;

    uint R = max(SimRes, 1u);

    // métriques anisotropes
    vec3 size = vec3(SimSizex, SimSizey, SimSizez);
    vec3 h    = size / float(R);
    vec3 invh2 = 1.0 / (h * h);   // (1/hx^2, 1/hy^2, 1/hz^2)

    // indices
    uint i =  id              % R;
    uint j = (id / R)         % R;
    uint k =  id / (R*R);
    ivec3 I  = ivec3(int(i), int(j), int(k));
    ivec3 lo = ivec3(0), hi = ivec3(int(R)-1);

    // pas de diffusion -> passthrough
    if (visc <= 0.0){
        U[id]     = TDIn_U();
        U_tmp[id] = TDIn_U_tmp();
        return;
    }

    // bord: no-slip
    if (TDIn_Flag() == 1u){
        vec3  bnd = TDIn_BndN();
        ivec3 Ii  = clamp(I - ivec3(int(bnd.x), int(bnd.y), int(bnd.z)), lo, hi);
        vec3 u_in = TDIn_U(0, flatten3(Ii, R));
        vec3 flip = vec3(bnd.x != 0.0 ? -1.0 : 1.0,
                         bnd.y != 0.0 ? -1.0 : 1.0,
                         bnd.z != 0.0 ? -1.0 : 1.0);
        U[id]     = u_in * flip;
        U_tmp[id] = TDIn_U_tmp(); // RHS inchangé
        return;
    }

    // voisins
    ivec3 L = clamp(I + ivec3(-1, 0, 0), lo, hi);
    ivec3 Rr= clamp(I + ivec3( 1, 0, 0), lo, hi);
    ivec3 D = clamp(I + ivec3( 0,-1, 0), lo, hi);
    ivec3 Uu= clamp(I + ivec3( 0, 1, 0), lo, hi);
    ivec3 B = clamp(I + ivec3( 0, 0,-1), lo, hi);
    ivec3 F = clamp(I + ivec3( 0, 0, 1), lo, hi);

    vec3 uL = TDIn_U(0, flatten3(L,  R));
    vec3 uR = TDIn_U(0, flatten3(Rr, R));
    vec3 uD = TDIn_U(0, flatten3(D,  R));
    vec3 uU = TDIn_U(0, flatten3(Uu, R));
    vec3 uB = TDIn_U(0, flatten3(B,  R));
    vec3 uF = TDIn_U(0, flatten3(F,  R));

    // RHS constant (champ advecté) pendant toutes les passes
    vec3 uStar = TDIn_U_tmp();

    // Formule anisotrope:
    // (I - ν dt ∇²) u = uStar
    // Jacobi: u_new = ( uStar + ν dt * [ (uL+uR)/hx^2 + (uD+uU)/hy^2 + (uB+uF)/hz^2 ] )
    //                    / ( 1 + ν dt * 2 * (1/hx^2 + 1/hy^2 + 1/hz^2) )
    vec3 weightedSum = (uL + uR) * invh2.x
                     + (uD + uU) * invh2.y
                     + (uB + uF) * invh2.z;

    float denom = 1.0 + visc * dt * 2.0 * (invh2.x + invh2.y + invh2.z);
    vec3  uNext = (uStar + visc * dt * weightedSum) / denom;

    U[id]     = uNext;
    U_tmp[id] = uStar;
}
