// WCSim's standard ROOT output -> plain text for to_hits.py: every true photon hit (WCSimRootCherenkovHit /
// WCSimRootCherenkovHitTime of trigger 0, as sample-root-scripts/sample_readfile.C reads them) and the tube tables.
// HK copy: every PMT collection the file holds, each with its own tube-id space (WCSimRootGeom):
//   set 0  wcsimrootevent      the ID's first collection     geo->GetPMT(i)
//   set 1  wcsimrootevent2     the hybrid's second (mPMTs)   geo->GetPMT(i, true)
//   set 2  wcsimrootevent_OD   the OD                        geo->GetODPMT(i)
//   root -l -b -q 'dump_hits.C("in.root", "out")'   ->  out_hits.csv (set, evt, tube, t_ns), out_tubes.csv (set, tube,
//   x, y, z [cm], dx, dy, dz, mpmt, mpmt_pmt)        (libWCSimRoot loaded and WCSim's include/ on the include path: run.sh)
#include <fstream>
#include "TFile.h"
#include "TTree.h"
#include "TClonesArray.h"
#include "WCSimRootEvent.hh"
#include "WCSimRootGeom.hh"

void dump_hits(const char* in, const char* out) {
  TFile* f = TFile::Open(in, "read");
  TTree* tree = (TTree*)f->Get("wcsimT");
  TTree* gt = (TTree*)f->Get("wcsimGeoT");
  WCSimRootGeom* geo = 0;
  gt->SetBranchAddress("wcsimrootgeom", &geo);
  gt->GetEntry(0);
  const char* br[3] = {"wcsimrootevent", "wcsimrootevent2", "wcsimrootevent_OD"};
  int ntube[3] = {geo->GetWCNumPMT(), geo->GetWCNumPMT(true), geo->GetODWCNumPMT()};
  WCSimRootEvent* ev[3] = {0, 0, 0};
  bool use[3];
  for (int s = 0; s < 3; s++) {
    use[s] = tree->GetBranch(br[s]) != 0 && ntube[s] > 0;
    if (!tree->GetBranch(br[s])) continue;
    if (!use[s]) { tree->SetBranchStatus(br[s], 0); continue; }
    ev[s] = new WCSimRootEvent();
    tree->GetBranch(br[s])->SetAddress(&ev[s]);
    tree->GetBranch(br[s])->SetAutoDelete(kTRUE);
  }
  std::ofstream ft(std::string(out) + "_tubes.csv");
  ft << "set,tube,x,y,z,dx,dy,dz,mpmt,mpmt_pmt\n";
  for (int s = 0; s < 3; s++) {
    if (!use[s]) continue;
    for (int i = 0; i < ntube[s]; i++) {
      WCSimRootPMT p = s == 2 ? geo->GetODPMT(i) : geo->GetPMT(i, s == 1);
      ft << s << "," << p.GetTubeNo() << "," << p.GetPosition(0) << "," << p.GetPosition(1) << "," << p.GetPosition(2)
         << "," << p.GetOrientation(0) << "," << p.GetOrientation(1) << "," << p.GetOrientation(2) << ","
         << p.GetmPMTNo() << "," << p.GetmPMT_PMTNo() << "\n";
    }
  }
  std::ofstream fh(std::string(out) + "_hits.csv");
  fh << "set,evt,tube,t\n";
  long n[3] = {0, 0, 0};
  for (long e = 0; e < tree->GetEntries(); e++) {
    tree->GetEntry(e);
    for (int s = 0; s < 3; s++) {
      if (!use[s]) continue;
      WCSimRootTrigger* tr = ev[s]->GetTrigger(0);
      TClonesArray* times = tr->GetCherenkovHitTimes();
      for (int h = 0; h < tr->GetNcherenkovhits(); h++) {
        WCSimRootCherenkovHit* ch = (WCSimRootCherenkovHit*)tr->GetCherenkovHits()->At(h);
        int i0 = ch->GetTotalPe(0), np = ch->GetTotalPe(1);
        for (int k = i0; k < i0 + np; k++) {
          WCSimRootCherenkovHitTime* t = (WCSimRootCherenkovHitTime*)times->At(k);
          fh << s << "," << e << "," << ch->GetTubeID() << "," << t->GetTruetime() << "\n";
          n[s]++;
        }
      }
    }
  }
  printf("dump_hits: %lld events, %ld hits, %d tubes; sets id/mpmt/od: hits %ld %ld %ld, tubes %d %d %d\n",
         tree->GetEntries(), n[0] + n[1] + n[2], (use[0] ? ntube[0] : 0) + (use[1] ? ntube[1] : 0) +
         (use[2] ? ntube[2] : 0), n[0], n[1], n[2], use[0] ? ntube[0] : 0, use[1] ? ntube[1] : 0,
         use[2] ? ntube[2] : 0);
}
