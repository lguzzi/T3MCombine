from __future__ import print_function
import ROOT
import os
import gc; gc.disable()
import argparse
parser = argparse.ArgumentParser('''
This script is a python adaptation of the HNL discrete profiling c++ code
https://github.com/BParkHNLs/flashggFinalFit/blob/mg-branch/Background/test/fTest.cpp
NOTE: input files must contain a branch called 'mass' and possibly be already skimmed.
NOTE: the code will probably crash on exit. This is somehow related to the RooChi2Var object.
'''
)
parser.add_argument('-b', '--binning'   , nargs=3  , type=float, default=[40, 1.6, 2.0]       , help='mass binning as nbins low hig (GeV)')
parser.add_argument('-c', '--category'  ,            type=str  , default='W_C17'              , help='category to fit'                    )
parser.add_argument('-m', '--mass'      ,            type=str  , default='cand_refit_tau_mass', help='name of the 3mu mass variable'      )
parser.add_argument('-t', '--tree'      ,            type=str  , default='tree'               , help='name of the input tree'             )
parser.add_argument('-M', '--max-order' ,            type=int  , default=6                    , help='max pdf order to consider'          )
parser.add_argument('-U', '--unblind'   , action='store_true'                                 , help='don\'t use blinded ranges'          )
args = parser.parse_args()

ROOT.gROOT.SetBatch(True)
if not os.path.exists('MultiPdfWorkspaces'):
  os.makedirs("MultiPdfWorkspaces")

files   = {
  'W_A17': '/gwpool/users/lguzzi/Tau3Mu/2017_2018/combine_test/T3MuCombine/python/W_snapshots/data/A17.root',
  'W_B17': '/gwpool/users/lguzzi/Tau3Mu/2017_2018/combine_test/T3MuCombine/python/W_snapshots/data/B17.root',
  'W_C17': '/gwpool/users/lguzzi/Tau3Mu/2017_2018/combine_test/T3MuCombine/python/W_snapshots/data/C17.root',
  'W_A18': '/gwpool/users/lguzzi/Tau3Mu/2017_2018/combine_test/T3MuCombine/python/W_snapshots/data/A18.root',
  'W_B18': '/gwpool/users/lguzzi/Tau3Mu/2017_2018/combine_test/T3MuCombine/python/W_snapshots/data/B18.root',
  'W_C18': '/gwpool/users/lguzzi/Tau3Mu/2017_2018/combine_test/T3MuCombine/python/W_snapshots/data/C18.root',
}

mass = ROOT.RooRealVar(args.mass, '3#mu mass', args.binning[1], args.binning[2], 'GeV')
mass.setRange('unblinded', 1.6, 2.0)
mass.setRange('left', 1.6, 1.74)
mass.setRange('right', 1.82, 2)
pdfs = ROOT.RooWorkspace('pdfs')

getattr(pdfs, 'import')(mass)

file = ROOT.TFile(files[args.category], 'READ')
tree = file.Get(args.tree)
args.max_order = max(min(args.max_order, tree.GetEntries()-3), 1)

c_powerlaw = ROOT.RooRealVar("c_PowerLaw_{}".format(args.category), "", 1, -10, 10)
powerlaw = ROOT.RooGenericPdf("PowerLaw", "TMath::Power(@0, @1)", ROOT.RooArgList(mass, c_powerlaw))

pdfs.factory("Exponential::Exponential({}, slope_{}[0, -10, 10])".format(args.mass, args.category))
getattr(pdfs, 'import')(powerlaw)

# Bernstein: oder n has n+1 coefficients (starts from constant)
# Chebychev: order n has n coefficients (starts from linear)
for i in range(0, args.max_order+1):
  c_bernstein = '{'+','.join(['c_Bernstein{}{}_{}[.1, 0, 1]'   .format(i, j, args.category) for j in range(i+1)])+'}'
  pdfs.factory('Bernstein::Bernstein{}({}, {})'.format(i, args.mass, c_bernstein))
for i in range(args.max_order):
  c_chebychev = '{'+','.join(['c_Chebychev{}{}_{}[.1, 0, 1]'.format(i+1, j, args.category) for j in range(i+1)])+'}'
  pdfs.factory('Chebychev::Chebychev{}({}, {})'.format(i+1, args.mass, c_chebychev))

wspace = ROOT.RooWorkspace('wspace')
getattr(wspace, 'import')(mass)
wspace.var(args.mass).setBins(args.binning[0])

data = ROOT.RooDataSet('data', '', tree, ROOT.RooArgSet(wspace.var(args.mass)))#.binnedClone('data')
hist = data.binnedClone('histo')
getattr(wspace, 'import')(data)

frame = wspace.var(args.mass).frame()
wspace.data('data').plotOn(frame)

envelope = ROOT.RooArgList("envelope")

can = ROOT.TCanvas()
leg = ROOT.TLegend(0.7, 0.6, 0.9, 0.9)

gofmax  = 0
bestfit = None
families = ['Bernstein', 'Chebychev', 'Exponential', 'PowerLaw']
allpdfs_list = ROOT.RooArgList(pdfs.allPdfs())
allpdfs_list = [allpdfs_list.at(j) for j in range(allpdfs_list.getSize())]

for j, fam in enumerate(families):
  pdf_list = [p for p in allpdfs_list if p.GetName().startswith(fam)]
  mnlls    = []
  for i, pdf in enumerate(pdf_list):
    norm = ROOT.RooRealVar("nev", "", 0, 1e+3)
    ext_pdf = ROOT.RooAddPdf(pdf.GetName()+"_ext", "", ROOT.RooArgList(pdf), ROOT.RooArgList(norm))
    results = ext_pdf.fitTo(data,  ROOT.RooFit.Save(True), ROOT.RooFit.Range('unblinded' if args.unblind else 'left,right'), ROOT.RooFit.Extended(True))
    chi2 = ROOT.RooChi2Var("chi2"+pdf.GetName(), "", pdf, hist)
    mnll = results.minNll()+(i+1)

    gof_prob = ROOT.TMath.Prob(chi2.getVal(), hist.numEntries()-pdf.getParameters(data).selectByAttrib("Constant", False).getSize())
    fis_prob = ROOT.TMath.Prob(2.*(mnlls[-1]-mnll), 1) if len(mnlls) else 0
    
    mnlls.append(mnll)

    print(">>>", pdf.GetName(), gof_prob, fis_prob)

    if gof_prob > 0.01 and fis_prob < 0.1:
      if gof_prob > gofmax:
        gofmax = mnll
        bestfit = pdf.GetName()
      envelope.add(pdf)
      pdf.plotOn(frame, ROOT.RooFit.LineColor(envelope.getSize()), ROOT.RooFit.Name(pdf.GetName()), ROOT.RooFit.Range('unblinded' if args.unblind else 'left,right'))
    del chi2 # RooChi2Var makes the code crash at the end of the execution. This line makes it crash faster.
for pdf in [envelope.at(i) for i in range(envelope.getSize())]:
  leg.AddEntry(frame.findObject(pdf.GetName()), pdf.GetName()+" (bestfit)" if bestfit==pdf.GetName() else pdf.GetName(), "l")

frame.Draw()
leg.Draw("SAME")
can.Update()
can.Modified()
cat = ROOT.RooCategory("roomultipdf_cat_{}".format(args.category), "")

multipdf = ROOT.RooMultiPdf("multipdf", "", cat, envelope)
cat.setIndex([envelope.at(i).GetName() for i in range(envelope.getSize())].index(bestfit))
outerspace = ROOT.RooWorkspace('ospace')
getattr(outerspace, 'import')(envelope)
getattr(outerspace, 'import')(multipdf)

can.SaveAs("MultiPdfWorkspaces/"+args.category+"_plot.pdf", "pdf")
outerspace.writeToFile("MultiPdfWorkspaces/"+args.category+".root")

print("\nExecution is complete. I may crash in peace\n")
