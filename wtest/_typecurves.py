from matplotlib import pyplot

import numpy

from scipy import integrate

from scipy.optimize import root_scalar

from scipy.sparse import csr_matrix as csr
from scipy.sparse.linalg import spsolve as sps

from scipy.special import expi

from scipy.special import j0 as BJ0
from scipy.special import j1 as BJ1
from scipy.special import y0 as BY0
from scipy.special import y1 as BY1

class dimless():
    """Calculates well bottomhole pressure in field units for the given
    constant flow rate oil production, single phase flow.
    """

    def __init__(self,res,oil,well):
        """Initializes reservoir, oil and well properties."""
        
        self.k = res.permeability
        self.phi = res.porosity
        self.h = res.width
        self.cr = res.compressibility

        self.muo = oil.viscosity
        self.co = oil.compressibility
        self.Bo = oil.formation_volume_factor
        self.rhoo = oil.density

        self.qo = well.rate
        self.tp = well.time
        self.rw = well.radius
        self.skin = well.skin
        self.Awb = (numpy.pi*well.radius**2)/4

    def set_irreducible(self,water,saturation):
        """Sets the irreducible water saturation amount and water properties."""

        self.muw = water.viscosity
        self.cw = water.compressibility
        self.Bw = water.formation_volume_factor

        self.Swirr = saturation

    def set_compressibility(self,total=None):
        """Sets the total compressibility. If None,
        it will try to calculate it from rock and fluid compressibilities."""

        if total is not None:
            self.ct = total
            return

        self.cr = 0 if self.cr is None else self.cr

        if hasattr(self,"Swirr"):
            if self.Swirr>0:
                self.cf = (1-self.Swirr)*self.co+self.Swirr*self.cw
            else:
                self.cf = self.co

        if hasattr(self,"cf"):
            if self.cf is None:
                self.cf = self.co
        else:
            self.cf = self.co

        self.ct = self.cr+self.cf

    def set_wellborestorage(self):

        self.Cs = (144*self.Awb)/(5.615*self.rhoo)

    def initialize(self,time=None,size=50,scale='linear'):
        """It calculates delta bottom hole flowing pressure for constant
        flow rate production at transient state, exponential integral solution.
        """

        if time is not None:
            self.time = time[time>=self.twell]

        else:

            if scale == "linear":
                self.time = numpy.linspace(self.twell,self.tp,size)
            elif scale == "log":
                self.time = numpy.logspace(*numpy.log10([self.twell,self.tp]),size)

            self._scale = scale

        Ei = expi(-39.5*(self.rw**2)/(self.eta*self.time))

        self._delta = -self.flowterm*(1/2*Ei-self.skin)

    def set_dimensionless(self,pinitial):

        self.pD = (self.k*self.h)/(141.2*self.qo*self.Bo*self.muo)*(pinitial-self.delta)

        self.tD = (0.00632829*self.k*self.time)/(self.phi*self.muo*self.ct*self.rw**2)

        self.CD = (0.8936*self.Cs)/(self.phi*self.ct*self.h*self.rw**2)

    def set_boundary(self,radius=None,area=None):
        """Sets the radius of outer circular boundary, ft and calculates
        pseudo steady state solution correcting pressure for boundary effects.
        
        If area is not None, the radius is calculated from area [acre].
        """

        if area is not None:
            radius = numpy.sqrt(area*43560/numpy.pi)

        self._radius = radius

        pseudo_cond = self.time>=self.tbound

        pseudo_time = self.time[pseudo_cond]

        term_time = -0.012648*(self.eta*pseudo_time)/self.radius**2

        term_boundary = -numpy.log(self.radius/self.rw)

        delta = -self.flowterm*(term_time+term_boundary+3/4-self.skin)

        self._delta[pseudo_cond] = delta

    def view(self,axis=None,pinitial=None,scale=None):

        showFlag = True if axis is None else False

        if axis is None:
            figure,axis = pyplot.subplots(nrows=1,ncols=1)

        if pinitial is None:
            yaxis,ylabel = -self.delta,f"Wellbore Pressure Drop [psi]"
        else:
            yaxis,ylabel = pinitial+self.delta,"Wellbore Pressure [psi]"

        axis.plot(self.time,yaxis)

        if scale is None:
            try:
                scale = self._scale
            except AttributeError:
                scale = "linear"

        axis.set_xscale(scale)

        if pinitial is None:
            axis.invert_yaxis()

        axis.set_xlabel("Time [days]")
        axis.set_ylabel(ylabel)

        if showFlag:
            pyplot.show()

    @property
    def eta(self):

        return self.k/(self.phi*self.muo*self.ct)

    @property
    def flowterm(self):

        return -141.2*(self.qo*self.Bo*self.muo)/(self.k*self.h)

    @property
    def radius(self):

        return self._radius

    @property
    def delta(self):

        return self._delta

    @property
    def twell(self):

        return 15802*self.rw**2/self.eta

    @property
    def tbound(self):

        return 39.5*self.radius**2/self.eta

class everdingen():

    @staticmethod
    def pressure(tD):

        tD = numpy.array(tD).flatten()

        pwD = numpy.zeros(tD.shape)

        for index,time in enumerate(tD):

            umin = numpy.sqrt(1/time)/1e6
            umax = numpy.sqrt(1/time)*1e5

            u = numpy.logspace(numpy.log10(umin),numpy.log10(umax),2000)

            y = everdingen.pressure_integrand(u,time)
            z = integrate.simpson(y,u)

            pwD[index] = 4*z/numpy.pi**2

        return pwD

    @staticmethod
    def pressure_integrand(u,tD):
        """Integral kernel of the equation #VI-24, page 313"""

        tD = numpy.array(tD).flatten()

        term1 = 1-numpy.exp(-u**2*tD)
        term2 = BJ1(u)**2+BY1(u)**2

        return term1/(u**3*term2)

    @staticmethod
    def pressure_bounded(tD,R,numterms=2):

        tD,R = numpy.array(tD).flatten(),float(R)

        term1 = 2/(R**2-1)*(1/4.+tD)

        term2 = (3*R**4-4*R**4*numpy.log(R)-2*R**2-1)/(4*(R**2-1)**2)

        tD = tD.reshape((-1,1))

        betan = everdingen.pressure_bounded_find_roots(R,numterms)

        # print(f"{R=} {betan=}")

        betan = betan.reshape((1,-1))

        term3a = numpy.exp(-betan**2*tD)*BJ1(betan*R)**2

        term3b = betan**2*(BJ1(betan*R)**2-BJ1(betan)**2)

        term3 = (term3a/term3b).sum(axis=1)

        return term1-term2+2*term3

    @staticmethod
    def pressure_bounded_find_roots(R,numterms=2):

        roots = numpy.empty(numterms)

        for index in range(numterms):

            lower_bound = ((2*index+1)*numpy.pi)/(2*R-2)
            upper_bound = ((2*index+3)*numpy.pi)/(2*R-2)

            bracket = (lower_bound,upper_bound)

            solver = root_scalar(everdingen.pressure_bounded_root_function,
                args=(R,),method="brentq",bracket=bracket)

            roots[index] = solver.root

        return roots

    @staticmethod
    def pressure_bounded_root_function(beta,R):

        return BJ1(beta*R)*BY1(beta)-BJ1(beta)*BY1(beta*R)

class agarwal():
    """
    tD  : dimensionless time (k*t)/(phi*mu*ct*rw**2)
    CD  : dimensionless wellbore storage constant C/(2*pi*phi*h*ct*rw**2)
    SF  : skin factor, dimensionless
    """

    gamma = 0.57722

    @staticmethod
    def pressure(tD,CD=0,SF=0):
        """Returns the pressure solution to diffusivity equation for the well with
            - finite dimensions,
            - wellbore storage effect,
            - skin effect,
            - infinite reservoir
        Equation # 9, page 281
        """

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        if CD==0:
            return 1/2*(numpy.log(4*tD)-agarwal.gamma)+SF

        u = numpy.logspace(-8,1,2000)
        # u = numpy.linspace(1e-8,1e1,100000)

        if SF<0:
            TSF,SF = SF,0
            tD = tD*numpy.exp(2*TSF)
            CD = CD*numpy.exp(2*TSF)
            u = u/numpy.exp(2*TSF)

        pwD = numpy.zeros(tD.shape)

        for index,time in enumerate(tD):
            y = agarwal.pressure_integrand(u,time,CD,SF)
            z = integrate.simpson(y,u)

            pwD[index] = 4*z/numpy.pi**2

        return pwD

    @staticmethod
    def pressure_integrand(u,tD,CD=0,SF=0):
        """Integral kernel of the equation # 9, page 281"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        term1 = 1-numpy.exp(-u**2*tD)
        term2 = u*CD*BJ0(u)-(1-CD*SF*u**2)*BJ1(u)
        term3 = u*CD*BY0(u)-(1-CD*SF*u**2)*BY1(u)

        return term1/(u**3*(term2**2+term3**2))

    @staticmethod
    def pressure_lineSource(tD,CD=0,SF=0):
        """Equation # 11, page 281"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        u = numpy.logspace(-8,1,2000)

        if SF<0:
            TSF,SF = SF,0
            tD *= numpy.exp(2*TSF)
            CD *= numpy.exp(2*TSF)
            u /= numpy.exp(2*TSF)

        pwDline = numpy.zeros(tD.shape)

        for index,time in enumerate(tD):
            y = agarwal.pressure_lineSource_integrand(u,time,CD,SF)
            z = integrate.simpson(y,u)

            pwDline[index] = z

        return pwDline

    @staticmethod
    def pressure_lineSource_integrand(u,tD,CD=0,SF=0):
        """Internal kernel of the equation # 11, page 281"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        term1 = (1-numpy.exp(-u**2*tD))*BJ0(u)
        term2 = 1-u**2*CD*SF+1/2*numpy.pi*u**2*CD*BY0(u)
        term3 = 1/2*numpy.pi*CD*u**2*BJ0(u)

        return term1/(u*(term2**2+term3**2))

    @staticmethod
    def pressure_shorttime(tD,CD=0,SF=0):
        """Short-time approximation of pressure equation, Equation #14 & 15, page 282"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        if SF==0 and CD!=0:
            term1 = tD-(4*tD**(3/2))/(3*CD*numpy.sqrt(numpy.pi))

            return 1/CD*term1

        elif SF!=0 and CD!=0:
            term1 = tD-(tD**2)/(2*CD*SF)
            term2 = (8*tD**(5/2))/(15*numpy.sqrt(numpy.pi)*CD*SF**2)

            return 1/CD*(term1+term2)

        else:
            raise Warning("Not Implemented")

    @staticmethod
    def pressure_longtime(tD,CD=0,SF=0):
        """Long-time approximation of pressure equation, Equation #13, page 282"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        term1 = numpy.log(4*tD)-agarwal.gamma
        term2 = term1+2*SF

        return 1/2*(term2+1/(2*tD)*(term1+1-2*CD*term2))

    @staticmethod
    def derivative(tD,CD=0,SF=0):
        """Equation #26, page 284"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        pwDder = numpy.zeros(tD.shape)

        for index,time in enumerate(tD):
            u = numpy.logspace(-8,-1,1000)
            y = agarwal.derivative_integrand(u,time,CD,SF)
            z = integrate.simpson(y,u)

            pwDder[index] = 4*CD*z/numpy.pi**2

        return pwDder

    @staticmethod
    def derivative_integrand(u,tD,CD=0,SF=0):
        """Integral kernel of the equation 26, page 284"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        term1 = numpy.exp(-u**2*tD)
        term2 = u*CD*BJ0(u)-(1-CD*SF*u**2)*BJ1(u)
        term3 = u*CD*BY0(u)-(1-CD*SF*u**2)*BY1(u)

        return term1/(u*(term2**2+term3**2))

    @staticmethod
    def derivative_shorttime(tD,CD=0,SF=0):
        """Short-time approximation, equation 27 & 28, page 284"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        if SF==0 and CD!=0:
            return (1-2*numpy.sqrt(tD/numpy.pi)/CD+1/CD*(1/CD-1/2)*tD)/CD
        elif SF!=0 and CD!=0:
            return (1-tD/(CD*SF))

    @staticmethod
    def derivative_longtime(tD,CD=0,SF=0):
        """Long-time approximation, equation 29, page 284"""

        tD,CD,SF = numpy.array(tD).flatten(),float(CD),float(SF)

        term1 = CD/(2*tD)
        term2 = CD**2/(2*tD**2)*(2*SF-1)
        term3 = CD*(1-2*CD)/(4*tD**2)*(numpy.log(4*tD)-agarwal.gamma)

        return (term1+term2-term3)

class finite():

    def __init__(self,R,rskin=1,alpha=1,nimpaired=None,nunharmed=None):
        """
        R         : reservoir radius

        rskin     : radius of impaired zone

        alpha     : permeability reduction in the impaired zone,
                    k_impaired/k_unharmed

        nimpaired : number of grids in the impaired zone
        nunharmed : number of grids in the unharmed zone
        """

        self.R = R

        self.rskin = rskin
        self.alpha = alpha

        self.nimpaired = nimpaired
        self.nunharmed = nunharmed

        self.node = self.setnode()
        self.grid = self.setgrid()

        self.width_grid = self.setwidth()
        self.alpha_grid = self.setalpha()

    def pressure(self,tD,CD=0):
        """
        tD        : times to calculate well pressure
        CD        : dimensionless storage
        """
        
        #static part of transmissibility
        beta_inner,beta_outer = self.betas()

        #creating time steps
        timesteps = tD[1:]-tD[:-1]
        timesteps = numpy.insert(timesteps,0,timesteps[0])

        #initialization of pressure arrays
        press = numpy.zeros(self.size)
        pwell = numpy.zeros(timesteps.size+1)

        N,indices = self.size,self.indices

        for index,timestep in enumerate(timesteps,start=1):

            BetaL = beta_inner*timestep
            BetaR = beta_outer*timestep
            BetaC = 1+BetaL+BetaR

            theta1,theta2 = self.thetas(CD,timestep,pwell[index-1])

            BetaC[0] = 1+BetaR[0]*(1+theta2) # inner boundary correction
            BetaC[-1] = 1+BetaL[-1] # outer boundary correction

            Tmat = csr((N,N))
            
            Tmat += csr((BetaC,(indices,indices)),shape=(N,N))
            Tmat += csr((-BetaL[1:],(indices[1:],indices[:-1])),shape=(N,N))
            Tmat += csr((-BetaR[:-1],(indices[:-1],indices[1:])),shape=(N,N))

            press[0] += BetaL[0]*theta1

            press = sps(Tmat,press)

            pimag = theta1+(1-theta2)*press[0]

            pwell[index] = (pimag+press[0])/2

        return pwell[1:]

    def derivative(self):

        pass

    def setnode(self):

        R,r = self.R,self.rskin

        nimpaired = self.nimpaired
        nunharmed = self.nunharmed

        if nimpaired is None:
            nimpaired = int(numpy.ceil(r-1).tolist())

            if nimpaired != 0:
                nimpaired = max(nimpaired,50)

        if nunharmed is None:
            nunharmed = 50

        outer = numpy.log10((r,R))

        impaired = numpy.linspace(*(1,r),nimpaired+1)
        unharmed = numpy.logspace(*outer,nunharmed+1)

        return numpy.append(impaired,unharmed[1:])

    def setgrid(self):
        
        return (self.node[1:]+self.node[:-1])/2

    def setwidth(self):

        return (self.node[1:]-self.node[:-1])

    def setalpha(self):

        array = numpy.ones(self.size)

        border = (self.node<self.rskin).sum()

        array[:border] = self.alpha

        return array

    def betas(self):

        nwidth = self.nodewidth()
        nalpha = self.nodealpha()

        nbeta = self.node*nalpha/nwidth

        betaL = nbeta[:-1]/self.grid/self.width_grid
        betaR = nbeta[1:]/self.grid/self.width_grid

        return betaL,betaR

    def thetas(self,storage,timestep,pwell):

        term1 = self.alpha_grid[0]/self.width_grid[0]
        term2 = storage/timestep

        term3 = term1+term2/2

        return (1+term2*pwell)/term3,term2/term3

    def nodewidth(self):

        gwidth = self.width_grid

        gwidth = numpy.insert(gwidth,0,gwidth[0])
        gwidth = numpy.append(gwidth,gwidth[-1])

        return (gwidth[1:]+gwidth[:-1])/2

    def nodealpha(self):

        center = self.grid

        center = numpy.insert(center,0,center[0]-self.width_grid[0])
        center = numpy.append(center,center[-1]+self.width_grid[-1])

        galpha = self.alpha_grid

        galpha = numpy.insert(galpha,0,galpha[0])
        galpha = numpy.append(galpha,galpha[-1])

        radrad = numpy.log(center[1:]/center[:-1])
        nodrad = numpy.log(self.node/center[:-1])/galpha[:-1]
        radnod = numpy.log(center[1:]/self.node)/galpha[1:]

        return radrad/(nodrad+radnod)

    @property
    def skin(self):

        return (1/self.alpha-1)*numpy.log(self.rskin)

    @property
    def size(self):

        return self.node.size-1

    @property
    def indices(self):

        return numpy.arange(self.size)

if __name__ == "__main__":

    print(finite.setnode(10,r=2.5))

    # tD = 1e-2

    # umin = numpy.sqrt(1/tD)/1e6
    # umax = numpy.sqrt(1/tD)*1e5

    # u = numpy.logspace(numpy.log10(umin),numpy.log10(umax),2000)

    # y1 = everdingen.pressure_integrand(u,tD)
    # y2 = everdingen.pressure_integrand(u,1e8)
    # y1 = everdingen.pressure_integrand(u,0.0001)

    # y1 = agarwal.pressure_integrand(u,1e8,1e5,0)
    # y2 = agarwal.pressure_integrand(u,1e8,1e5,0)
    # y2 = agarwal.pressure_lineSource_integrand(u,1e3,10000,0)
    # y3 = agarwal.pressure_lineSource_integrand(u,1e3,10000,5)
    # y4 = agarwal.pressure_lineSource_integrand(u,1e3,10000,10)
    # y5 = agarwal.pressure_lineSource_integrand(u,1e3,10000,20)

    # print(f"{agarwal.pressure(1e8,1e5,0)[0]:8.5f}")

    # pyplot.loglog(u,y1)
    # pyplot.loglog(u,y1)
    # pyplot.loglog(u,y2)
    # pyplot.loglog(u,y3)
    # pyplot.loglog(u,y4)
    # pyplot.loglog(u,y5)

    # pyplot.show()



