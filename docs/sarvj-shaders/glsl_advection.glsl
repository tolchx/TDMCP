	uint flatten3(ivec3 c, uint R){ return uint(c.x) + R * (uint(c.y) + R * uint(c.z)); }
	
	// Interpole U aux centres autour d'une position monde x
	vec3 sampleU_trilinear(vec3 x, vec3 bmin, vec3 h, uint R){
	    // coords de grille: les centres sont à (i + 0.5)
	    vec3 g = (x - bmin) / h - vec3(0.5);
		
	    ivec3 i0 = ivec3(floor(g));
	    ivec3 i1 = i0 + ivec3(1);
	    // fraction [0,1]
	    vec3 f = clamp(fract(g), 0.0, 1.0);
	
	    // clamp indices aux bords
	    ivec3 lo = ivec3(0);
	    ivec3 hi = ivec3(int(R) - 1);
	    i0 = clamp(i0, lo, hi);
	    i1 = clamp(i1, lo, hi);
	
	    // fetch 8 voisins dans le champ U d'entrée
	    vec3 c000 = TDIn_U(0, flatten3(ivec3(i0.x, i0.y, i0.z), R));
	    vec3 c100 = TDIn_U(0, flatten3(ivec3(i1.x, i0.y, i0.z), R));
	    vec3 c010 = TDIn_U(0, flatten3(ivec3(i0.x, i1.y, i0.z), R));
	    vec3 c110 = TDIn_U(0, flatten3(ivec3(i1.x, i1.y, i0.z), R));
	    vec3 c001 = TDIn_U(0, flatten3(ivec3(i0.x, i0.y, i1.z), R));
	    vec3 c101 = TDIn_U(0, flatten3(ivec3(i1.x, i0.y, i1.z), R));
	    vec3 c011 = TDIn_U(0, flatten3(ivec3(i0.x, i1.y, i1.z), R));
	    vec3 c111 = TDIn_U(0, flatten3(ivec3(i1.x, i1.y, i1.z), R));
	
	    // trilinéaire
	    vec3 c00 = mix(c000, c100, f.x);
	    vec3 c10 = mix(c010, c110, f.x);
	    vec3 c01 = mix(c001, c101, f.x);
	    vec3 c11 = mix(c011, c111, f.x);
	    vec3 c0  = mix(c00,  c10,  f.y);
	    vec3 c1  = mix(c01,  c11,  f.y);
	    return mix(c0, c1, f.z);
	}
	
	void main() {
		const uint id = TDIndex();
		if(id >= TDNumElements())
			return;
		
		vec3 pos = TDIn_P();
		vec3 u = TDIn_U();
		vec3 u_tmp = TDIn_U_tmp();
	
		uint R = max(SimRes,1u);
		vec3 bmin = vec3(-.5*SimSizex,-.5*SimSizey,-.5*SimSizez);
		vec3 size = vec3(SimSizex,SimSizey,SimSizez);
		vec3 h = size/float(R);
		vec3 bmax = bmin+size;
	
		//Advection
		vec3 x_back = clamp(pos - dt*u, bmin + 0.5*h, bmax - 0.5*h);
		vec3 u_adv = sampleU_trilinear(x_back,bmin,h,R);
	
		if (TDIn_Flag() == 1u){
			u_adv = vec3(0.0);
		}
		u = u_adv;
		u_tmp = u_adv;
	
		U[id] = u;
		U_tmp[id] = u_tmp;
	}
	