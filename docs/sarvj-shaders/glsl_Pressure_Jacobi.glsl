// Pressure_Jacobi_Aniso.glsl
uint flatten3(ivec3 c, uint R){
    return uint(c.x) + R*(uint(c.y) + R*uint(c.z));
}

void main(){
    const uint id = TDIndex(); if (id >= TDNumElements()) return;

    uint R = max(SimRes,1u);

    // métriques anisotropes
    vec3 size = vec3(SimSizex,SimSizey,SimSizez);
    vec3 h    = size / float(R);
    vec3 invh2 = 1.0 / (h * h);

    // indices
    uint i =  id              % R;
    uint j = (id / R)         % R;
    uint k =  id / (R*R);
    ivec3 I = ivec3(int(i),int(j),int(k));
    ivec3 lo=ivec3(0), hi=ivec3(int(R)-1);

    // BC pression: Neumann (copie voisin intérieur)
    if (TDIn_Flag() == 1u){
        vec3  bnd = TDIn_BndN();
        ivec3 Ii  = clamp(I - ivec3(int(bnd.x),int(bnd.y),int(bnd.z)), lo, hi);
        float p_in = TDIn_Press(0, flatten3(Ii, R));
        Press[id]  = p_in;
        return;
    }

    // voisins
    ivec3 L = clamp(I + ivec3(-1,0,0), lo, hi);
    ivec3 Rr= clamp(I + ivec3( 1,0,0), lo, hi);
    ivec3 D = clamp(I + ivec3(0,-1,0), lo, hi);
    ivec3 Uu= clamp(I + ivec3(0, 1,0), lo, hi);
    ivec3 B = clamp(I + ivec3(0,0,-1), lo, hi);
    ivec3 F = clamp(I + ivec3(0,0, 1), lo, hi);

    float pL = TDIn_Press(0, flatten3(L,  R));
    float pR = TDIn_Press(0, flatten3(Rr, R));
    float pD = TDIn_Press(0, flatten3(D,  R));
    float pU = TDIn_Press(0, flatten3(Uu, R));
    float pB = TDIn_Press(0, flatten3(B,  R));
    float pF = TDIn_Press(0, flatten3(F,  R));

    float div = TDIn_Div();

    // Jacobi anisotrope pour ∇² p = div :
    // p_new = ( (pL+pR)/hx^2 + (pD+pU)/hy^2 + (pB+pF)/hz^2 - div )
    //         / ( 2*(1/hx^2 + 1/hy^2 + 1/hz^2) )
    float numerator = (pL + pR) * invh2.x
                    + (pD + pU) * invh2.y
                    + (pB + pF) * invh2.z
                    - div;

    float denom = 2.0 * (invh2.x + invh2.y + invh2.z);

    float pNext = numerator / denom;

    Press[id] = pNext;
}
